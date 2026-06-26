"""
Langflow Component: PDF Knowledge Search
PDF를 knowledge base처럼 검색 — 쿼리와 관련된 표·그림을 추출하여 반환.

컴포넌트 (langflow.custom.Component 기반, Langflow 1.x+ 호환)
  ① PDFKnowledgeSearchComponent  ← 메인 (Search Query 연결)
  ② PDFToJsonComponent           ← 전체-JSON 변환 (후처리용)

그림·표 저장 방식
  - PyMuPDF(fitz) 로 페이지를 렌더링 후 bbox 영역을 크롭 → PNG 저장
  - 래스터 이미지 + 벡터 그래픽 모두 탐지 (fitz.get_images + get_drawings 클러스터링)
  - 인덱싱 시점에 전체 저장 → 검색 시 이미 저장된 이미지 재사용
  - 각 이미지에 연관 텍스트(셀/캡션/주변 문장)를 연결하여 유사도 스코어링에 사용
"""

from __future__ import annotations

import base64
import http.server
import io
import json
import re
import socket as _socket
import socketserver
import threading
from pathlib import Path
from typing import Optional

import pdfplumber

# ── 이미지 파일 서버 (Chat Output에서 HTTP URL로 이미지 표시) ─────────────────
_img_server_lock = threading.Lock()
_img_server: Optional[socketserver.TCPServer] = None
_img_server_port: int = 0
_img_server_dir: str = ""


def _start_image_server(directory: str, port: int = 8765) -> str:
    """
    이미지 디렉토리를 서빙하는 로컬 HTTP 서버를 시작하고 base URL을 반환.
    이미 같은 디렉토리로 실행 중이면 재사용.
    반환값: 'http://localhost:{port}' (Chat Output Markdown 이미지 URL 용)

    주의: Langflow와 브라우저가 같은 머신에 있을 때만 동작.
          Docker / 원격 서버 환경에서는 이미지 대신 파일 경로가 표시됨.
    """
    global _img_server, _img_server_port, _img_server_dir

    directory = str(Path(directory).resolve())

    with _img_server_lock:
        if _img_server is not None and _img_server_dir == directory:
            return f"http://localhost:{_img_server_port}"

        # 사용 가능한 포트 탐색 (지정 포트 ~ +50)
        actual_port = port
        for p in range(port, port + 50):
            try:
                with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as s:
                    s.bind(("", p))
                actual_port = p
                break
            except OSError:
                continue

        class _Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=directory, **kwargs)

            def log_message(self, fmt, *args):
                pass  # 액세스 로그 억제

        httpd = socketserver.TCPServer(
            ("", actual_port), _Handler, bind_and_activate=False
        )
        httpd.allow_reuse_address = True
        httpd.server_bind()
        httpd.server_activate()

        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()

        _img_server = httpd
        _img_server_port = actual_port
        _img_server_dir = directory

        print(f"[ImageServer] 이미지 서버 시작: http://localhost:{actual_port}  ← {directory}")
        return f"http://localhost:{actual_port}"

# ── Langflow imports ──────────────────────────────────────────────────────────
from langflow.custom import Component
from langflow.schema import Data
from langflow.schema.message import Message
from langflow.io import (
    BoolInput,
    DropdownInput,
    FileInput,
    FloatInput,
    IntInput,
    MessageTextInput,
    Output,
    SecretStrInput,
    StrInput,
)


# ══════════════════════════════════════════════════════════════════════════════
# §1  유사도 스코어링
# ══════════════════════════════════════════════════════════════════════════════

def _tokenize(text: str) -> list[str]:
    return re.findall(r"[가-힣a-zA-Z0-9]+", text.lower())


def _tf(tokens: list[str]) -> dict[str, float]:
    total = len(tokens) or 1
    freq: dict[str, float] = {}
    for t in tokens:
        freq[t] = freq.get(t, 0) + 1
    return {k: v / total for k, v in freq.items()}


def compute_similarity(query: str, document: str) -> float:
    """TF-IDF cosine (sklearn) 또는 TF-weighted Jaccard 폴백. 반환 0.0~1.0"""
    if not query.strip() or not document.strip():
        return 0.0
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity as _cos
        vec = TfidfVectorizer(token_pattern=r"[가-힣a-zA-Z0-9]+")
        tfidf = vec.fit_transform([query, document])
        return float(_cos(tfidf[0:1], tfidf[1:2])[0][0])
    except Exception:
        q_tf = _tf(_tokenize(query))
        d_tf = _tf(_tokenize(document))
        keys = set(q_tf) | set(d_tf)
        if not keys:
            return 0.0
        dot = sum(q_tf.get(k, 0) * d_tf.get(k, 0) for k in keys)
        norm = (sum(v ** 2 for v in q_tf.values()) ** 0.5) * \
               (sum(v ** 2 for v in d_tf.values()) ** 0.5)
        return dot / norm if norm else 0.0


# ══════════════════════════════════════════════════════════════════════════════
# §2  이미지 렌더링 (PyMuPDF 기반)
# ══════════════════════════════════════════════════════════════════════════════

def _render_region_png(
    pdf_path: str,
    page_num: int,
    bbox: tuple,          # (x0, y0, x1, y1) — pdfplumber / fitz 공통 좌표 (y=0 at top)
    out_path: Path,
    dpi: int = 150,
    padding: int = 4,
) -> bool:
    """
    PDF 페이지의 bbox 영역을 PNG로 렌더링하여 저장.
    PyMuPDF(fitz) 필수. pip install pymupdf
    """
    try:
        import fitz
    except ImportError:
        print("  [Render] PyMuPDF 미설치 — pip install pymupdf 후 재시도")
        return False

    try:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        doc = fitz.open(str(pdf_path))
        page = doc[page_num - 1]
        pw, ph = page.rect.width, page.rect.height

        x0, y0, x1, y1 = bbox
        clip = fitz.Rect(
            max(0.0, x0 - padding), max(0.0, y0 - padding),
            min(pw, x1 + padding), min(ph, y1 + padding),
        )
        if clip.is_empty or clip.get_area() < 1:
            print(f"  [Render] bbox가 너무 작거나 빈 영역: {bbox}")
            doc.close()
            return False

        mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        pix = page.get_pixmap(matrix=mat, clip=clip, alpha=False)
        pix.save(str(out_path))
        doc.close()
        return True
    except Exception as e:
        print(f"  [Render] 렌더링 실패 ({e})")
        return False




# ══════════════════════════════════════════════════════════════════════════════
# §3  그림 영역 탐지 (PyMuPDF — 래스터 + 벡터 그래픽)
# ══════════════════════════════════════════════════════════════════════════════

def _cluster_rects(rects, gap: int = 15):
    """겹치거나 gap pt 이내의 fitz.Rect들을 반복 병합하여 클러스터 반환"""
    if not rects:
        return []
    try:
        import fitz
        merged = list(rects)
        changed = True
        while changed:
            changed = False
            used = [False] * len(merged)
            result = []
            for i, r1 in enumerate(merged):
                if used[i]:
                    continue
                cluster = fitz.Rect(r1)
                expanded = fitz.Rect(
                    r1.x0 - gap, r1.y0 - gap, r1.x1 + gap, r1.y1 + gap
                )
                for j, r2 in enumerate(merged):
                    if i == j or used[j]:
                        continue
                    if expanded.intersects(r2):
                        cluster |= r2
                        used[j] = True
                        changed = True
                result.append(cluster)
                used[i] = True
            merged = result
        return merged
    except Exception:
        return rects


def _deduplicate_bboxes(bboxes: list[tuple]) -> list[tuple]:
    """다른 bbox에 완전히 포함되는 bbox를 제거"""
    result = []
    for i, b1 in enumerate(bboxes):
        x0, y0, x1, y1 = b1
        contained = False
        for j, b2 in enumerate(bboxes):
            if i == j:
                continue
            bx0, by0, bx1, by1 = b2
            if bx0 <= x0 and by0 <= y0 and bx1 >= x1 and by1 >= y1:
                if (bx1 - bx0) * (by1 - by0) > (x1 - x0) * (y1 - y0):
                    contained = True
                    break
        if not contained:
            result.append(b1)
    return result


def _detect_figure_regions(
    pdf_path: str,
    page_num: int,
    table_bboxes: list[tuple],
    min_area: float = 2000,
) -> list[tuple]:
    """
    PyMuPDF로 페이지에서 그림 영역 탐지.
    ① 래스터 이미지 bbox
    ② 벡터 그래픽(drawing) 클러스터링
    표 영역과 겹치는 후보는 제외.
    """
    try:
        import fitz
    except ImportError:
        print("  [Figure] PyMuPDF 없음 — 그림 탐지 불가 (pip install pymupdf)")
        return []

    try:
        doc = fitz.open(str(pdf_path))
        page = doc[page_num - 1]
        candidates: list = []

        # ① 래스터 이미지
        for img_info in page.get_images(full=True):
            try:
                r = page.get_image_bbox(img_info)
                if r.is_valid and not r.is_empty and r.get_area() >= 100:
                    candidates.append(fitz.Rect(r))
            except Exception:
                pass

        # ② 벡터 그래픽 클러스터링
        draw_rects = []
        for d in page.get_drawings():
            r = d.get("rect")
            if r:
                fr = fitz.Rect(r)
                if not fr.is_empty and fr.get_area() > 10:
                    draw_rects.append(fr)

        clusters = _cluster_rects(draw_rects, gap=15)
        for cr in clusters:
            if cr.get_area() >= min_area:
                candidates.append(cr)

        doc.close()

        # 표 영역과 겹치는 후보 제외
        table_rects = [fitz.Rect(b) for b in table_bboxes]
        filtered = [
            (c.x0, c.y0, c.x1, c.y1)
            for c in candidates
            if not any(c.intersects(tr) for tr in table_rects)
        ]

        return _deduplicate_bboxes(filtered)

    except Exception as e:
        print(f"  [Figure] 탐지 오류: {e}")
        return []


# ══════════════════════════════════════════════════════════════════════════════
# §4  텍스트 유틸
# ══════════════════════════════════════════════════════════════════════════════

def _nearby_text(full_text: str, anchor: str, chars: int) -> str:
    pos = full_text.find(anchor[:20]) if anchor else -1
    if pos == -1:
        return full_text[:chars]
    start = max(0, pos - chars // 2)
    end = min(len(full_text), pos + len(anchor) + chars // 2)
    return full_text[start:end]


def _detect_caption(page_text: str) -> str:
    """'Figure X' / 'Fig. X' / '그림 X' 형식 캡션 첫 번째 매칭 반환"""
    m = re.search(
        r"(?:Figure|Fig\.?|그림)\s*[\dA-Za-z\-\.]+[^\n]*",
        page_text, re.IGNORECASE
    )
    return m.group(0).strip() if m else ""


# ══════════════════════════════════════════════════════════════════════════════
# §5  표·그림 요소 추출 (텍스트 + 이미지 저장)
# ══════════════════════════════════════════════════════════════════════════════

def _extract_table_elements(
    page,
    pdf_path: str,
    output_dir: Path,
    dpi: int,
) -> list[dict]:
    """페이지의 모든 표를 추출 — 셀 텍스트 + bbox 크롭 PNG 저장"""
    elements = []
    page_text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
    found_tables = page.find_tables()
    raw_tables = page.extract_tables()

    for t_idx, raw_table in enumerate(raw_tables):
        if not raw_table:
            continue

        headers = [str(c).strip() if c else "" for c in raw_table[0]]
        rows = []
        for raw_row in raw_table[1:]:
            row = {headers[ci]: (str(cell).strip() if cell else "")
                   for ci, cell in enumerate(raw_row)}
            rows.append(row)

        bbox = None
        try:
            tbbox = found_tables[t_idx].bbox
            bbox = (tbbox[0], tbbox[1], tbbox[2], tbbox[3])
        except Exception:
            pass

        # 표 셀 텍스트 + 주변 컨텍스트 → 검색용 텍스트
        cell_text = " ".join([
            " ".join(headers),
            " ".join(str(v) for row in rows for v in row.values()),
            _nearby_text(page_text, " ".join(headers), 300),
        ])

        # PNG 파일 저장 (외부 활용 + HTTP 서버로 Chat Output 표시)
        img_path = None
        if bbox:
            out_path = output_dir / f"page{page.page_number}_table{t_idx}.png"
            print(f"  [Table] Page {page.page_number} / 표{t_idx} 렌더링 → {out_path.name}")
            if _render_region_png(pdf_path, page.page_number, bbox, out_path, dpi):
                img_path = str(out_path)
                print(f"  [Table] 저장 완료: {out_path.name}")
            else:
                print(f"  [Table] 이미지 저장 실패")

        elements.append({
            "type": "table",
            "page_number": page.page_number,
            "index": t_idx,
            "bbox": bbox,
            "headers": headers,
            "rows": rows,
            "text_content": cell_text,
            "image_path": img_path,
            "score": 0.0,
        })

    return elements


def _extract_figure_elements(
    page,
    pdf_path: str,
    output_dir: Path,
    dpi: int,
    table_bboxes: list[tuple],
) -> list[dict]:
    """페이지의 모든 그림을 탐지 — 캡션/내부 텍스트 + bbox 크롭 PNG 저장"""
    elements = []
    page_text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
    caption = _detect_caption(page_text)

    figure_bboxes = _detect_figure_regions(
        pdf_path, page.page_number, table_bboxes
    )
    print(f"  [Figure] Page {page.page_number}: 그림 영역 {len(figure_bboxes)}개 탐지")

    for f_idx, bbox in enumerate(figure_bboxes):
        x0, y0, x1, y1 = bbox

        # 그림 내부 텍스트 (pdfplumber crop)
        inner_text = ""
        try:
            cropped = page.crop((x0, y0, x1, y1))
            inner_text = cropped.extract_text() or ""
        except Exception:
            pass

        # 검색용 텍스트: 캡션 + 내부 텍스트 + 주변 맥락
        anchor = caption or inner_text[:40]
        context = _nearby_text(page_text, anchor, 400)
        text_content = " ".join(filter(None, [caption, inner_text, context]))

        # PNG 파일 저장 (외부 활용 + HTTP 서버로 Chat Output 표시)
        img_path = None
        out_path = output_dir / f"page{page.page_number}_fig{f_idx}.png"
        print(f"  [Figure] Page {page.page_number} / 그림{f_idx} 렌더링 → {out_path.name}")
        if _render_region_png(pdf_path, page.page_number, bbox, out_path, dpi):
            img_path = str(out_path)
            print(f"  [Figure] 저장 완료: {out_path.name}")
        else:
            print(f"  [Figure] 이미지 저장 실패")

        elements.append({
            "type": "figure",
            "page_number": page.page_number,
            "index": f_idx,
            "bbox": bbox,
            "caption": caption,
            "inner_text": inner_text,
            "text_content": text_content,
            "image_path": img_path,
            "score": 0.0,
        })

    return elements


# ══════════════════════════════════════════════════════════════════════════════
# §6  PDF 인덱스 클래스
# ══════════════════════════════════════════════════════════════════════════════

class PDFIndex:
    """
    PDF 전체를 인덱싱 — 모든 표·그림을 이미지로 저장하고
    연관 텍스트와 함께 메모리에 보관.
    """

    def __init__(
        self,
        pdf_path: str,
        output_dir: str = "./pdf_elements",
        dpi: int = 150,
        password: Optional[str] = None,
    ):
        self.pdf_path = Path(pdf_path)
        self.output_dir = Path(output_dir)
        self.dpi = dpi
        self.metadata: dict = {}
        self.pages_text: list[str] = []
        self.elements: list[dict] = []   # 표 + 그림 통합 목록
        self._load(password)

    @property
    def tables(self) -> list[dict]:
        return [e for e in self.elements if e["type"] == "table"]

    @property
    def figures(self) -> list[dict]:
        return [e for e in self.elements if e["type"] == "figure"]

    def _load(self, password: Optional[str]):
        print(f"[PDF] 파일 열기: {self.pdf_path.name}")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        kwargs = {"password": password} if password else {}

        with pdfplumber.open(self.pdf_path, **kwargs) as pdf:
            raw_meta = pdf.metadata or {}
            total = len(pdf.pages)
            self.metadata = {
                "file_name": self.pdf_path.name,
                "total_pages": total,
                "title": raw_meta.get("Title", ""),
                "author": raw_meta.get("Author", ""),
                "creator": raw_meta.get("Creator", ""),
            }
            print(f"[PDF] 총 {total}페이지 — 페이지별 파싱·저장 시작")

            for page in pdf.pages:
                pn = page.page_number
                print(f"  [Page {pn}/{total}] 텍스트 추출 중...")
                text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
                self.pages_text.append(text)

                # ── 표 추출 ───────────────────────────────────────────────
                print(f"  [Page {pn}/{total}] 표(Table) 추출 및 이미지 저장 중...")
                tbl_elements = _extract_table_elements(
                    page, str(self.pdf_path), self.output_dir, self.dpi
                )
                self.elements.extend(tbl_elements)
                print(f"  [Page {pn}/{total}] 표 {len(tbl_elements)}개 완료")

                # ── 그림 추출 ─────────────────────────────────────────────
                print(f"  [Page {pn}/{total}] 그림(Figure) 탐지 및 이미지 저장 중...")
                tbl_bboxes = [e["bbox"] for e in tbl_elements if e["bbox"]]
                fig_elements = _extract_figure_elements(
                    page, str(self.pdf_path), self.output_dir, self.dpi, tbl_bboxes
                )
                self.elements.extend(fig_elements)
                print(f"  [Page {pn}/{total}] 그림 {len(fig_elements)}개 완료")

        print(
            f"[PDF] 인덱싱 완료 — "
            f"표 {len(self.tables)}개 / 그림 {len(self.figures)}개 "
            f"(저장 위치: {self.output_dir.resolve()})"
        )

    # ── 검색 ──────────────────────────────────────────────────────────────────

    def _search_elements(
        self,
        query: str,
        top_k: int,
        threshold: float,
        types: tuple = ("table", "figure"),
    ) -> list[dict]:
        candidates = [e for e in self.elements if e["type"] in types]
        print(f"[Search] 유사도 스코어링 — 후보 {len(candidates)}개 ({', '.join(types)}) / 임계값 {threshold}")
        scored = []
        for elem in candidates:
            score = compute_similarity(query, elem["text_content"])
            if score >= threshold:
                scored.append({**elem, "score": score})
        scored.sort(key=lambda x: x["score"], reverse=True)
        result = scored[:top_k]
        print(f"[Search] 결과: {len(result)}건 (상위 {top_k}개 반환)")
        return result

    def search_tables(self, query: str, top_k: int = 5, threshold: float = 0.05) -> list[dict]:
        return self._search_elements(query, top_k, threshold, types=("table",))

    def search_figures(self, query: str, top_k: int = 5, threshold: float = 0.05) -> list[dict]:
        return self._search_elements(query, top_k, threshold, types=("figure",))

    def search_text_chunks(
        self,
        query: str,
        top_k: int = 5,
        threshold: float = 0.05,
        chunk_size: int = 500,
        overlap: int = 100,
    ) -> list[dict]:
        chunks = []
        for page_idx, text in enumerate(self.pages_text):
            for start in range(0, max(1, len(text) - overlap), chunk_size - overlap):
                chunk = text[start: start + chunk_size]
                if chunk.strip():
                    chunks.append({"page_number": page_idx + 1, "text": chunk, "score": 0.0})

        print(f"[Search] 본문 청크 유사도 스코어링 — 후보 {len(chunks)}개 / 임계값 {threshold}")
        scored = []
        for c in chunks:
            score = compute_similarity(query, c["text"])
            if score >= threshold:
                scored.append({**c, "score": score})
        scored.sort(key=lambda x: x["score"], reverse=True)
        result = scored[:top_k]
        print(f"[Search] 본문 결과: {len(result)}건")
        return result


# ══════════════════════════════════════════════════════════════════════════════
# §7  마크다운 결과 포매터 (Parser / ChatOutput 호환)
# ══════════════════════════════════════════════════════════════════════════════

def table_to_markdown(table: dict) -> str:
    headers = table["headers"]
    rows = table["rows"]
    if not headers:
        return ""

    def _esc(s: str) -> str:
        return s.replace("|", "\\|").replace("\n", " ")

    lines = [
        "| " + " | ".join(_esc(h) for h in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_esc(row.get(h, "")) for h in headers) + " |")
    return "\n".join(lines)


def format_search_results(
    query: str,
    metadata: dict,
    text_chunks: list[dict],
    tables: list[dict],
    figures: list[dict],
    server_url: Optional[str] = None,
) -> str:
    """검색 결과를 Markdown으로 직렬화.
    server_url이 있으면 HTTP URL로 이미지를 표시 (가장 안정적).
    server_url이 없으면 파일 경로 텍스트로 표시.

    Langflow Chat Output은 data: URI와 HTML img 태그를 모두 차단하므로
    로컬 HTTP 서버를 통한 실제 URL만이 이미지를 정상 표시함."""
    lines: list[str] = []

    lines += [
        "# PDF Knowledge Search", "",
        f"**검색어**: `{query}`  ",
        f"**파일**: {metadata.get('file_name', '')}  ",
        f"**총 페이지**: {metadata.get('total_pages', '')}",
    ]
    if server_url:
        lines += [f"**이미지 서버**: {server_url}", ""]
    else:
        lines += [""]

    # ── 관련 본문 ─────────────────────────────────────────────────────────────
    if text_chunks:
        lines += ["---", "", f"## 관련 본문 ({len(text_chunks)}건)", ""]
        for i, chunk in enumerate(text_chunks, 1):
            chunk_text = chunk["text"].strip().replace("\n", "  \n> ")
            lines += [
                f"### 본문 {i}  —  Page {chunk['page_number']}  (관련도 {int(chunk['score']*100)}%)",
                "", f"> {chunk_text}", "",
            ]

    # ── 관련 표 ───────────────────────────────────────────────────────────────
    if tables:
        lines += ["---", "", f"## 관련 표 ({len(tables)}건)", ""]
        for i, tbl in enumerate(tables, 1):
            lines += [
                f"### Table {i}  —  Page {tbl['page_number']}  (관련도 {int(tbl['score']*100)}%)", "",
            ]
            img_path = tbl.get("image_path")
            if img_path and server_url:
                # HTTP URL → Markdown 이미지 (브라우저가 정상 렌더링)
                url = f"{server_url}/{Path(img_path).name}"
                lines += [f"![Table {i}]({url})", ""]
            elif img_path:
                lines += [f"📎 `{img_path}`", ""]
            # 표 텍스트 (Markdown 표)
            lines += [table_to_markdown(tbl), ""]

    # ── 관련 그림 ─────────────────────────────────────────────────────────────
    if figures:
        lines += ["---", "", f"## 관련 그림 ({len(figures)}건)", ""]
        for i, fig in enumerate(figures, 1):
            lines += [
                f"### Figure {i}  —  Page {fig['page_number']}  (관련도 {int(fig['score']*100)}%)", "",
            ]
            if fig.get("caption"):
                lines += [f"**캡션**: {fig['caption']}", ""]
            img_path = fig.get("image_path")
            if img_path and server_url:
                # HTTP URL → Markdown 이미지 (브라우저가 정상 렌더링)
                url = f"{server_url}/{Path(img_path).name}"
                lines += [f"![Figure {i}]({url})", ""]
            elif img_path:
                lines += [f"📎 `{img_path}`", ""]
            else:
                lines += ["*(이미지 없음 — pip install pymupdf 후 재시도)*", ""]

    if not (text_chunks or tables or figures):
        lines += ["", "> 검색 결과 없음. 쿼리를 바꾸거나 유사도 임계값을 낮춰보세요.", ""]

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# §8  기존 전체-JSON 변환 함수
# ══════════════════════════════════════════════════════════════════════════════

def convert_pdf_to_json(
    pdf_path: str,
    extract_images: bool = True,
    extract_word_positions: bool = False,
    password: Optional[str] = None,
) -> dict:
    """PDF 전체를 구조화된 JSON dict로 변환"""
    print(f"[Convert] PDF 로딩: {Path(pdf_path).name}")
    index = PDFIndex(pdf_path, output_dir="./pdf_elements_json", password=password)
    pages_data = []

    kwargs = {"password": password} if password else {}
    with pdfplumber.open(pdf_path, **kwargs) as pdf:
        for page in pdf.pages:
            pn = page.page_number
            print(f"  [Page {pn}] JSON 변환 중...")
            raw_text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""

            images_meta = []
            if extract_images:
                for img_obj in page.images:
                    images_meta.append({
                        "image_index": len(images_meta),
                        "name": img_obj.get("name", ""),
                        "width": img_obj.get("width"),
                        "height": img_obj.get("height"),
                        "x0": img_obj.get("x0"), "y0": img_obj.get("y0"),
                        "x1": img_obj.get("x1"), "y1": img_obj.get("y1"),
                        "colorspace": img_obj.get("colorspace"),
                    })

            tbl_elems = [e for e in index.elements
                         if e["type"] == "table" and e["page_number"] == pn]
            tables_data = [{k: v for k, v in e.items()
                            if k not in ("score", "base64_uri", "text_content")}
                           for e in tbl_elems]

            words = []
            if extract_word_positions:
                for w in page.extract_words(x_tolerance=3, y_tolerance=3):
                    words.append({"text": w["text"], "x0": w["x0"],
                                  "y0": w["top"], "x1": w["x1"], "y1": w["bottom"]})

            entry = {
                "page_number": pn,
                "width": page.width, "height": page.height,
                "text": re.sub(r"\n{3,}", "\n\n", raw_text).strip(),
                "tables": tables_data,
                "images": images_meta,
            }
            if extract_word_positions:
                entry["words"] = words
            pages_data.append(entry)

    print(f"[Convert] 완료 — {len(pages_data)}페이지 / 표 {len(index.tables)}개 / 그림 {len(index.figures)}개")
    return {
        "metadata": index.metadata,
        "pages": pages_data,
        "summary": {
            "total_pages": index.metadata["total_pages"],
            "total_tables": len(index.tables),
            "total_images": len(index.figures),
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# §9  Langflow 컴포넌트
# ══════════════════════════════════════════════════════════════════════════════

class PDFKnowledgeSearchComponent(Component):
    """
    PDF를 knowledge base처럼 검색합니다.
    Search Query 입력을 Chat Input 등 다른 컴포넌트와 연결하세요.

    출력 포트
      • result  : Markdown (본문·표 텍스트+이미지·그림 이미지) → ChatOutput 연결
      • figures : 저장된 요소 경로 목록 (Data)
    """

    display_name = "PDF Knowledge Search"
    description = (
        "PDF에서 Search Query와 관련된 본문·표·그림을 추출하고 "
        "이미지와 함께 Markdown으로 반환합니다."
    )
    icon = "search"
    name = "PDFKnowledgeSearch"

    inputs = [
        FileInput(
            name="pdf_file", display_name="PDF 파일",
            file_types=["pdf"], required=True,
            info="검색할 PDF 파일을 업로드하세요.",
        ),
        MessageTextInput(
            name="search_query", display_name="Search Query", required=True,
            info="찾을 내용. Chat Input 등과 연결 가능합니다.",
        ),
        IntInput(
            name="top_k", display_name="최대 결과 수 (Top-K)", value=5,
            info="표·그림·본문 각각 최대 반환 건수.",
        ),
        FloatInput(
            name="similarity_threshold", display_name="유사도 임계값", value=0.05,
            info="0~1 사이. 낮을수록 더 많은 결과.",
        ),
        BoolInput(
            name="search_text", display_name="본문 검색 포함", value=True,
        ),
        BoolInput(
            name="search_tables", display_name="표(Table) 검색 포함", value=True,
        ),
        BoolInput(
            name="search_figures", display_name="그림(Figure) 검색 포함", value=True,
        ),
        StrInput(
            name="element_output_dir", display_name="이미지 저장 폴더",
            value="./pdf_elements",
            info="표·그림 PNG가 저장될 디렉토리. 절대 경로 권장.",
        ),
        IntInput(
            name="element_dpi", display_name="이미지 해상도 (DPI)", value=150,
            info="저장 PNG의 DPI (72~300).",
        ),
        IntInput(
            name="image_server_port", display_name="이미지 서버 포트", value=8765,
            info=(
                "Chat Output 이미지 표시용 HTTP 서버 포트. "
                "0으로 설정하면 비활성화 (파일 경로만 표시)."
            ),
        ),
        StrInput(
            name="image_server_host", display_name="이미지 서버 호스트", value="localhost",
            info=(
                "이미지 URL에 사용할 호스트명 또는 IP 주소.\n"
                "• 로컬 환경: localhost (기본값)\n"
                "• 원격 서버: Langflow가 실행 중인 서버의 IP 또는 도메인 "
                "(예: 192.168.1.100, my-server.example.com)\n"
                "브라우저에서 이 호스트의 이미지 서버 포트에 접근 가능해야 합니다."
            ),
        ),
        SecretStrInput(
            name="password", display_name="PDF 비밀번호 (선택)", value="",
        ),
    ]

    outputs = [
        Output(display_name="Markdown Result", name="result", method="search"),
        Output(display_name="Element Paths", name="element_paths", method="get_element_paths"),
    ]

    _cached_index: Optional[PDFIndex] = None
    _cached_path: str = ""

    def _get_index(self) -> PDFIndex:
        pdf_path = str(self.pdf_file)
        if self._cached_path != pdf_path:
            print(f"[Component] PDF 인덱싱 시작: {Path(pdf_path).name}")
            self._cached_index = PDFIndex(
                pdf_path=pdf_path,
                output_dir=self.element_output_dir,
                dpi=int(self.element_dpi),
                password=self.password or None,
            )
            self._cached_path = pdf_path
        else:
            print(f"[Component] 캐시된 인덱스 재사용: {Path(pdf_path).name}")
        return self._cached_index  # type: ignore[return-value]

    def search(self) -> Message:
        print(f"[Component] === PDF Knowledge Search 시작 ===")
        print(f"[Component] 쿼리: '{self.search_query}'")

        index = self._get_index()
        query = self.search_query

        text_chunks = []
        if self.search_text:
            print(f"[Component] [1/3] 본문 검색 중...")
            text_chunks = index.search_text_chunks(
                query, self.top_k, self.similarity_threshold
            )
        else:
            print(f"[Component] [1/3] 본문 검색 생략")

        matched_tables = []
        if self.search_tables:
            print(f"[Component] [2/3] 표 검색 중...")
            matched_tables = index.search_tables(
                query, self.top_k, self.similarity_threshold
            )
        else:
            print(f"[Component] [2/3] 표 검색 생략")

        matched_figures = []
        if self.search_figures:
            print(f"[Component] [3/3] 그림 검색 중...")
            matched_figures = index.search_figures(
                query, self.top_k, self.similarity_threshold
            )
        else:
            print(f"[Component] [3/3] 그림 검색 생략")

        # 이미지 HTTP 서버 시작
        server_url = None
        port = int(self.image_server_port)
        host = (self.image_server_host or "localhost").strip()
        if port > 0:
            output_dir = str(Path(self.element_output_dir).resolve())
            print(f"[Component] 이미지 서버 시작: port={port}, dir={output_dir}")
            _start_image_server(output_dir, port)
            # 브라우저에서 접근할 URL (server_host 기반)
            server_url = f"http://{host}:{port}"
            print(f"[Component] 이미지 서버 URL: {server_url}")
        else:
            print(f"[Component] 이미지 서버 비활성화 (port=0)")

        print(f"[Component] 결과 Markdown 생성 중...")
        md = format_search_results(
            query=query,
            metadata=index.metadata,
            text_chunks=text_chunks,
            tables=matched_tables,
            figures=matched_figures,
            server_url=server_url,
        )
        print(
            f"[Component] === 완료 — "
            f"본문 {len(text_chunks)}건 / 표 {len(matched_tables)}건 / 그림 {len(matched_figures)}건 ==="
        )
        return Message(text=md)

    def get_element_paths(self) -> Data:
        """저장된 표·그림 이미지 경로 전체 목록 반환"""
        print(f"[Component] Element Paths 출력 요청")
        index = self._get_index()
        paths = {
            "tables": [e["image_path"] for e in index.tables if e.get("image_path")],
            "figures": [e["image_path"] for e in index.figures if e.get("image_path")],
        }
        print(f"[Component] 표 이미지 {len(paths['tables'])}개 / 그림 이미지 {len(paths['figures'])}개")
        return Data(data=paths)


class PDFToJsonComponent(Component):
    """PDF 전체를 구조화된 JSON으로 변환 (후처리·파이프라인용)"""

    display_name = "PDF to JSON (Full)"
    description = "PDF의 모든 페이지에서 텍스트·표·이미지를 추출하여 JSON Data로 반환합니다."
    icon = "file-text"
    name = "PDFToJsonConverter"

    inputs = [
        FileInput(name="pdf_file", display_name="PDF 파일",
                  file_types=["pdf"], required=True),
        BoolInput(name="extract_images", display_name="이미지 메타데이터 추출", value=True),
        BoolInput(name="extract_word_positions", display_name="단어 위치 포함", value=False),
        DropdownInput(name="output_format", display_name="출력 형식",
                      options=["Data (구조화)", "JSON 문자열"], value="Data (구조화)"),
        SecretStrInput(name="password", display_name="PDF 비밀번호 (선택)", value=""),
    ]

    outputs = [Output(display_name="JSON Data", name="json_data", method="convert")]

    def convert(self) -> Data:
        pdf_name = Path(str(self.pdf_file)).name
        print(f"[Component] === PDF to JSON 변환 시작: {pdf_name} ===")
        result = convert_pdf_to_json(
            pdf_path=self.pdf_file,
            extract_images=self.extract_images,
            extract_word_positions=self.extract_word_positions,
            password=self.password or None,
        )
        s = result["summary"]
        print(f"[Component] 완료 — 페이지 {s['total_pages']}개 / 표 {s['total_tables']}개 / 이미지 {s['total_images']}개")
        if self.output_format == "JSON 문자열":
            return Data(data={"json_string": json.dumps(result, ensure_ascii=False, indent=2)})
        return Data(data=result)


# ══════════════════════════════════════════════════════════════════════════════
# §10  CLI 단독 실행
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="PDF Knowledge Search / JSON 변환")
    sub = parser.add_subparsers(dest="cmd")

    sp = sub.add_parser("search", help="쿼리와 관련된 표·그림·텍스트 검색")
    sp.add_argument("pdf_path")
    sp.add_argument("query")
    sp.add_argument("--top-k", type=int, default=5)
    sp.add_argument("--threshold", type=float, default=0.05)
    sp.add_argument("--output-dir", default="./pdf_elements")
    sp.add_argument("--dpi", type=int, default=150)
    sp.add_argument("--password", default=None)

    cp = sub.add_parser("convert", help="PDF 전체를 JSON으로 변환")
    cp.add_argument("pdf_path")
    cp.add_argument("--output", "-o", default=None)
    cp.add_argument("--no-images", action="store_true")
    cp.add_argument("--word-positions", action="store_true")
    cp.add_argument("--password", default=None)

    args = parser.parse_args()

    if args.cmd == "search":
        index = PDFIndex(args.pdf_path, args.output_dir, args.dpi, args.password)
        chunks = index.search_text_chunks(args.query, args.top_k, args.threshold)
        tables = index.search_tables(args.query, args.top_k, args.threshold)
        figs = index.search_figures(args.query, args.top_k, args.threshold)
        print("\n" + format_search_results(args.query, index.metadata, chunks, tables, figs))

    elif args.cmd == "convert":
        data = convert_pdf_to_json(
            args.pdf_path,
            extract_images=not args.no_images,
            extract_word_positions=args.word_positions,
            password=args.password,
        )
        out = args.output or str(Path(args.pdf_path).with_suffix(".json"))
        with open(out, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[✓] 저장: {out}")

    else:
        parser.print_help()
