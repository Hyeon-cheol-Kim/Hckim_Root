"""
Langflow Component: PDF Knowledge Search
PDF를 knowledge base처럼 검색 — 쿼리와 관련된 표·그림을 추출하여 반환.

컴포넌트 (langflow.custom.Component 기반, Langflow 1.x+ 호환)
  ① PDFKnowledgeSearchComponent  ← 메인 (Search Query 연결)
  ② PDFToJsonComponent           ← 기존 전체-JSON 변환 (후처리용)
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Optional

import pdfplumber

# ── Langflow ──────────────────────────────────────────────────────────────────
# Component/Data/Message/Input 클래스를 항상 정의한다.
# Langflow 환경이면 실제 클래스를, 아니면 더미 클래스를 사용한다.
# 이렇게 해야 컴포넌트 클래스가 모듈 최상위에 위치할 수 있고
# Langflow의 파일 스캐너가 정상적으로 인식한다.

try:
    from langflow.custom import Component
    from langflow.schema import Data
    from langflow.schema.message import Message

    try:
        # Langflow 1.x+ 신버전
        from langflow.io import (
            BoolInput,
            DropdownInput,
            FileInput,
            FloatInput,
            IntInput,
            MessageTextInput,
            SecretStrInput,
            StrInput,
            Output,
        )
    except ImportError:
        # 구버전 폴백
        from langflow.inputs import (  # type: ignore[no-redef]
            BoolInput,
            DropdownInput,
            FileInput,
            FloatInput,
            IntInput,
            MessageTextInput,
            SecretStrInput,
            StrInput,
        )
        from langflow.template import Output  # type: ignore[no-redef]

except ImportError:
    # ── Langflow 없이 단독 실행할 때 사용하는 더미 클래스 ──────────────────
    class Component:  # type: ignore[no-redef]
        inputs: list = []
        outputs: list = []

    class Data:  # type: ignore[no-redef]
        def __init__(self, data=None, **_):
            self.data = data or {}

    class Message:  # type: ignore[no-redef]
        def __init__(self, text="", **_):
            self.text = text

    def _dummy_input(**_):
        return None

    BoolInput = DropdownInput = FileInput = FloatInput = _dummy_input
    IntInput = MessageTextInput = SecretStrInput = StrInput = _dummy_input

    def Output(**_):  # type: ignore[no-redef]
        return None


# ══════════════════════════════════════════════════════════════════════════════
# §1  유사도 스코어링
# ══════════════════════════════════════════════════════════════════════════════

def _tokenize(text: str) -> list[str]:
    """소문자 단어 토큰 추출 (한글 포함)"""
    return re.findall(r"[가-힣a-zA-Z0-9]+", text.lower())


def _tf(tokens: list[str]) -> dict[str, float]:
    total = len(tokens) or 1
    freq: dict[str, float] = {}
    for t in tokens:
        freq[t] = freq.get(t, 0) + 1
    return {k: v / total for k, v in freq.items()}


def compute_similarity(query: str, document: str) -> float:
    """
    sklearn이 있으면 TF-IDF cosine, 없으면 TF-weighted Jaccard 폴백.
    반환값: 0.0 ~ 1.0
    """
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
        norm = (sum(v**2 for v in q_tf.values()) ** 0.5) * \
               (sum(v**2 for v in d_tf.values()) ** 0.5)
        return dot / norm if norm else 0.0


# ══════════════════════════════════════════════════════════════════════════════
# §2  표(Table) 추출 및 마크다운 변환
# ══════════════════════════════════════════════════════════════════════════════

def _extract_tables_with_context(page, context_chars: int = 300) -> list[dict]:
    """
    페이지에서 표를 추출하고 주변 텍스트(컨텍스트)를 함께 저장.
    컨텍스트는 유사도 스코어링에 사용됩니다.
    """
    results = []
    full_text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""

    found_tables = page.find_tables()
    raw_tables = page.extract_tables()

    for t_idx, raw_table in enumerate(raw_tables):
        if not raw_table:
            continue

        header = [str(c).strip() if c else "" for c in raw_table[0]]
        rows = []
        for raw_row in raw_table[1:]:
            row = {header[ci]: (str(cell).strip() if cell else "")
                   for ci, cell in enumerate(raw_row)}
            rows.append(row)

        bbox = None
        try:
            tbbox = found_tables[t_idx].bbox
            bbox = (tbbox[0], tbbox[1], tbbox[2], tbbox[3])
        except Exception:
            pass

        # 표 위치 근처의 텍스트를 컨텍스트로 추출
        context = _nearby_text(full_text, " ".join(header), context_chars)

        results.append({
            "table_index": t_idx,
            "page_number": page.page_number,
            "bbox": bbox,
            "headers": header,
            "rows": rows,
            "row_count": len(rows),
            "col_count": len(header),
            "context": context,
            "score": 0.0,
        })
    return results


def _nearby_text(full_text: str, anchor: str, chars: int) -> str:
    """full_text에서 anchor 앞뒤 chars 글자를 컨텍스트로 반환"""
    pos = full_text.find(anchor[:20]) if anchor else -1
    if pos == -1:
        return full_text[:chars]
    start = max(0, pos - chars // 2)
    end = min(len(full_text), pos + len(anchor) + chars // 2)
    return full_text[start:end]


def table_to_markdown(table: dict) -> str:
    """표 dict → GitHub Flavored Markdown 표"""
    headers = table["headers"]
    rows = table["rows"]
    if not headers:
        return ""

    def _esc(s: str) -> str:
        return s.replace("|", "\\|").replace("\n", " ")

    lines = ["| " + " | ".join(_esc(h) for h in headers) + " |",
             "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(_esc(row.get(h, "")) for h in headers) + " |")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# §3  그림(Figure) 추출 및 이미지 저장
# ══════════════════════════════════════════════════════════════════════════════

def _detect_caption(page_text: str, img_bbox: tuple, page_height: float) -> str:
    """
    이미지 아래쪽에 있는 'Figure X' / 'Fig. X' 형식 캡션 탐색.
    캡션 없으면 빈 문자열 반환.
    """
    pattern = re.compile(
        r"(?:Figure|Fig\.?|그림)\s*[\dA-Za-z\-\.]+[^\n]*", re.IGNORECASE
    )
    for m in pattern.finditer(page_text):
        return m.group(0).strip()
    return ""


def _extract_figures_with_context(page) -> list[dict]:
    """페이지에서 임베디드 이미지 메타데이터와 주변 텍스트 컨텍스트 추출"""
    page_text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
    results = []

    for img_idx, img_obj in enumerate(page.images):
        bbox = (
            img_obj.get("x0", 0),
            img_obj.get("y0", 0),
            img_obj.get("x1", 0),
            img_obj.get("y1", 0),
        )
        caption = _detect_caption(page_text, bbox, page.height)
        context = caption or page_text[:400]

        results.append({
            "image_index": img_idx,
            "page_number": page.page_number,
            "name": img_obj.get("name", ""),
            "width_pt": img_obj.get("width"),
            "height_pt": img_obj.get("height"),
            "bbox": bbox,
            "page_width": page.width,
            "page_height": page.height,
            "caption": caption,
            "context": context,
            "saved_path": None,
            "score": 0.0,
        })
    return results


def save_figure_image(
    pdf_path: str,
    figure: dict,
    output_dir: Path,
    dpi: int = 150,
) -> Optional[str]:
    """
    PDF의 특정 이미지 영역을 PNG로 저장. 저장된 경로 반환.

    시도 순서:
      1. PyMuPDF (fitz)  — 정밀 bbox 크롭
      2. pdf2image + Pillow — 페이지 렌더 후 크롭
      3. pdfplumber 내장 이미지 스트림 (래스터 이미지만)
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    page_num = figure["page_number"]
    img_idx = figure["image_index"]
    out_path = output_dir / f"page{page_num}_fig{img_idx}.png"

    if out_path.exists():
        return str(out_path)

    bbox = figure["bbox"]  # (x0, y0, x1, y1) in PDF pts

    # ── Method 1: PyMuPDF ────────────────────────────────────────────────────
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(str(pdf_path))
        pg = doc[page_num - 1]
        scale = dpi / 72.0
        mat = fitz.Matrix(scale, scale)
        clip = fitz.Rect(bbox[0], bbox[1], bbox[2], bbox[3])
        pix = pg.get_pixmap(matrix=mat, clip=clip, alpha=False)
        pix.save(str(out_path))
        doc.close()
        return str(out_path)
    except ImportError:
        pass
    except Exception:
        pass

    # ── Method 2: pdf2image + Pillow ─────────────────────────────────────────
    try:
        from pdf2image import convert_from_path
        from PIL import Image as PILImage

        pages_imgs = convert_from_path(
            str(pdf_path), dpi=dpi, first_page=page_num, last_page=page_num
        )
        if not pages_imgs:
            raise RuntimeError("pdf2image returned empty list")

        page_img = pages_imgs[0]
        iw, ih = page_img.size
        pw, ph = figure["page_width"], figure["page_height"]

        sx, sy = iw / pw, ih / ph
        x0, y0, x1, y1 = bbox
        # PDF 좌표: y=0 is bottom; PIL: y=0 is top
        px0 = int(x0 * sx)
        py0 = int((ph - y1) * sy)
        px1 = int(x1 * sx)
        py1 = int((ph - y0) * sy)

        cropped = page_img.crop((
            max(0, px0), max(0, py0),
            min(iw, px1), min(ih, py1),
        ))
        cropped.save(str(out_path), "PNG")
        return str(out_path)
    except ImportError:
        pass
    except Exception:
        pass

    # ── Method 3: pdfplumber 내장 스트림 (래스터 이미지) ────────────────────
    try:
        from PIL import Image as PILImage

        with pdfplumber.open(str(pdf_path)) as pdf:
            pg = pdf.pages[page_num - 1]
            raw_imgs = pg.images
            if img_idx < len(raw_imgs):
                stream = raw_imgs[img_idx].get("stream")
                if stream is not None:
                    raw_bytes = (stream.get_data()
                                 if hasattr(stream, "get_data")
                                 else bytes(stream))
                    pil_img = PILImage.open(io.BytesIO(raw_bytes))
                    pil_img.save(str(out_path), "PNG")
                    return str(out_path)
    except Exception:
        pass

    return None  # 모든 방법 실패


# ══════════════════════════════════════════════════════════════════════════════
# §4  전체 PDF 로딩 및 검색 엔진
# ══════════════════════════════════════════════════════════════════════════════

class PDFIndex:
    """PDF 한 파일의 표·그림·텍스트를 메모리에 인덱싱"""

    def __init__(self, pdf_path: str, password: Optional[str] = None):
        self.pdf_path = Path(pdf_path)
        self.metadata: dict = {}
        self.pages_text: list[str] = []
        self.tables: list[dict] = []
        self.figures: list[dict] = []
        self._load(password)

    def _load(self, password: Optional[str]):
        kwargs = {"password": password} if password else {}
        with pdfplumber.open(self.pdf_path, **kwargs) as pdf:
            raw_meta = pdf.metadata or {}
            self.metadata = {
                "file_name": self.pdf_path.name,
                "total_pages": len(pdf.pages),
                "title": raw_meta.get("Title", ""),
                "author": raw_meta.get("Author", ""),
                "creator": raw_meta.get("Creator", ""),
            }
            for page in pdf.pages:
                text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
                self.pages_text.append(text)
                self.tables.extend(_extract_tables_with_context(page))
                self.figures.extend(_extract_figures_with_context(page))

    # ── 검색 ──────────────────────────────────────────────────────────────────

    def search_tables(
        self, query: str, top_k: int = 5, threshold: float = 0.05
    ) -> list[dict]:
        scored = []
        for t in self.tables:
            doc = " ".join([
                " ".join(t["headers"]),
                " ".join(str(v) for row in t["rows"] for v in row.values()),
                t["context"],
            ])
            score = compute_similarity(query, doc)
            if score >= threshold:
                scored.append({**t, "score": score})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def search_figures(
        self, query: str, top_k: int = 5, threshold: float = 0.05
    ) -> list[dict]:
        scored = []
        for fig in self.figures:
            page_idx = fig["page_number"] - 1
            page_text = self.pages_text[page_idx] if page_idx < len(self.pages_text) else ""
            doc = " ".join([fig["caption"], fig["context"], page_text[:500]])
            score = compute_similarity(query, doc)
            if score >= threshold:
                scored.append({**fig, "score": score})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def search_text_chunks(
        self, query: str, top_k: int = 5, threshold: float = 0.05,
        chunk_size: int = 500, overlap: int = 100,
    ) -> list[dict]:
        chunks = []
        for page_idx, text in enumerate(self.pages_text):
            for start in range(0, max(1, len(text) - overlap), chunk_size - overlap):
                chunk = text[start: start + chunk_size]
                if chunk.strip():
                    chunks.append({
                        "page_number": page_idx + 1,
                        "text": chunk,
                        "score": 0.0,
                    })

        scored = []
        for c in chunks:
            score = compute_similarity(query, c["text"])
            if score >= threshold:
                scored.append({**c, "score": score})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]


# ══════════════════════════════════════════════════════════════════════════════
# §5  마크다운 결과 포매터 (Parser 컴포넌트 호환)
# ══════════════════════════════════════════════════════════════════════════════

def format_search_results(
    query: str,
    metadata: dict,
    text_chunks: list[dict],
    tables: list[dict],
    figures: list[dict],
) -> str:
    """
    검색 결과를 Markdown 문자열로 직렬화.
    Langflow의 Parser / ChatOutput 컴포넌트에 바로 연결 가능.
    """
    lines: list[str] = []

    lines += [
        f"# PDF Knowledge Search",
        f"",
        f"**검색어**: `{query}`  ",
        f"**파일**: {metadata.get('file_name', '')}  ",
        f"**총 페이지**: {metadata.get('total_pages', '')}",
        f"",
    ]

    # ── 관련 텍스트 ─────────────────────────────────────────────────────────
    if text_chunks:
        lines += [f"---", f"", f"## 관련 본문 ({len(text_chunks)}건)", ""]
        for i, chunk in enumerate(text_chunks, 1):
            score_pct = int(chunk["score"] * 100)
            chunk_text = chunk["text"].strip().replace("\n", "  \n> ")
            lines += [
                f"### 본문 {i}  —  Page {chunk['page_number']}  (관련도 {score_pct}%)",
                "",
                f"> {chunk_text}",
                "",
            ]

    # ── 관련 표 ─────────────────────────────────────────────────────────────
    if tables:
        lines += [f"---", f"", f"## 관련 표 ({len(tables)}건)", ""]
        for i, tbl in enumerate(tables, 1):
            score_pct = int(tbl["score"] * 100)
            lines += [
                f"### Table {i}  —  Page {tbl['page_number']}  (관련도 {score_pct}%)",
                f"",
            ]
            if tbl.get("context"):
                lines += [f"*{tbl['context'][:120].strip()}*", ""]
            lines += [table_to_markdown(tbl), ""]

    # ── 관련 그림 ─────────────────────────────────────────────────────────
    if figures:
        lines += [f"---", f"", f"## 관련 그림 ({len(figures)}건)", ""]
        for i, fig in enumerate(figures, 1):
            score_pct = int(fig["score"] * 100)
            saved = fig.get("saved_path")
            lines += [
                f"### Figure {i}  —  Page {fig['page_number']}  (관련도 {score_pct}%)",
                f"",
            ]
            if fig.get("caption"):
                lines += [f"**캡션**: {fig['caption']}", ""]
            if fig.get("context"):
                lines += [f"*{fig['context'][:120].strip()}*", ""]
            if saved:
                lines += [f"**저장 경로**: `{saved}`", f"", f"![Figure {i}]({saved})", ""]
            else:
                lines += [f"*(이미지 저장 실패 — PyMuPDF 또는 pdf2image 설치 권장)*", ""]

    if not (text_chunks or tables or figures):
        lines += ["", "> 검색 결과가 없습니다. 쿼리를 바꾸거나 유사도 임계값을 낮춰보세요.", ""]

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# §6  기존 전체-JSON 변환 함수 (후처리/파이프라인용)
# ══════════════════════════════════════════════════════════════════════════════

def convert_pdf_to_json(
    pdf_path: str,
    extract_images: bool = True,
    extract_word_positions: bool = False,
    password: Optional[str] = None,
) -> dict:
    """PDF 전체를 구조화된 JSON dict로 변환 (기존 기능 유지)"""
    index = PDFIndex(pdf_path, password)
    pages_data = []

    kwargs = {"password": password} if password else {}
    with pdfplumber.open(pdf_path, **kwargs) as pdf:
        for page in pdf.pages:
            pn = page.page_number
            raw_text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""

            images_meta = []
            if extract_images:
                for img_obj in page.images:
                    entry = {
                        "image_index": len(images_meta),
                        "name": img_obj.get("name", ""),
                        "width": img_obj.get("width"),
                        "height": img_obj.get("height"),
                        "x0": img_obj.get("x0"),
                        "y0": img_obj.get("y0"),
                        "x1": img_obj.get("x1"),
                        "y1": img_obj.get("y1"),
                        "colorspace": img_obj.get("colorspace"),
                        "bits_per_component": img_obj.get("bits"),
                    }
                    images_meta.append(entry)

            tables_data = []
            for t in _extract_tables_with_context(page):
                tables_data.append({k: v for k, v in t.items()
                                    if k not in ("score",)})

            words = []
            if extract_word_positions:
                for w in page.extract_words(x_tolerance=3, y_tolerance=3):
                    words.append({"text": w["text"], "x0": w["x0"],
                                  "y0": w["top"], "x1": w["x1"], "y1": w["bottom"]})

            entry = {
                "page_number": pn,
                "width": page.width,
                "height": page.height,
                "text": re.sub(r"\n{3,}", "\n\n", raw_text).strip(),
                "tables": tables_data,
                "images": images_meta,
            }
            if extract_word_positions:
                entry["words"] = words
            pages_data.append(entry)

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
# §7  Langflow 컴포넌트  (모듈 최상위 레벨 — if 블록 없음)
#     Component는 위 import 블록에서 항상 정의되므로 조건문 불필요.
# ══════════════════════════════════════════════════════════════════════════════


# ── ① Knowledge Search 컴포넌트 ──────────────────────────────────────────────

class PDFKnowledgeSearchComponent(Component):
    """
    PDF를 knowledge base처럼 검색합니다.
    Search Query 입력을 다른 컴포넌트(Chat Input 등)에서 연결하세요.

    출력 포트
      • result  : Markdown 텍스트 (Parser / ChatOutput 연결)
      • figures : 저장된 그림 경로 목록 (Data)
    """

    display_name = "PDF Knowledge Search"
    description = (
        "PDF에서 Search Query와 관련된 본문·표(Table)·그림(Figure)을 "
        "추출하고 Markdown으로 반환합니다."
    )
    icon = "search"
    name = "PDFKnowledgeSearch"

    inputs = [
        FileInput(
            name="pdf_file",
            display_name="PDF 파일",
            file_types=["pdf"],
            required=True,
            info="검색할 PDF 파일을 업로드하세요.",
        ),
        MessageTextInput(
            name="search_query",
            display_name="Search Query",
            required=True,
            info="찾을 내용을 입력하세요. Chat Input 등 다른 컴포넌트와 연결 가능합니다.",
        ),
        IntInput(
            name="top_k",
            display_name="최대 결과 수 (Top-K)",
            value=5,
            info="표·그림·텍스트 각각 최대 몇 건을 반환할지 설정합니다.",
        ),
        FloatInput(
            name="similarity_threshold",
            display_name="유사도 임계값",
            value=0.05,
            info="0~1 사이. 낮을수록 더 많은 결과, 높을수록 정밀 검색.",
        ),
        BoolInput(
            name="search_text",
            display_name="본문 검색 포함",
            value=True,
            info="쿼리와 관련된 본문 텍스트 청크를 함께 반환합니다.",
        ),
        BoolInput(
            name="search_tables",
            display_name="표(Table) 검색 포함",
            value=True,
            info="쿼리와 관련된 표를 Markdown 형식으로 반환합니다.",
        ),
        BoolInput(
            name="search_figures",
            display_name="그림(Figure) 검색 포함",
            value=True,
            info="쿼리와 관련된 그림을 이미지 파일로 저장하고 경로를 반환합니다.",
        ),
        StrInput(
            name="figure_output_dir",
            display_name="그림 저장 폴더",
            value="./pdf_figures",
            info="추출된 그림이 저장될 디렉토리 경로.",
        ),
        IntInput(
            name="figure_dpi",
            display_name="그림 해상도 (DPI)",
            value=150,
            info="저장할 그림의 DPI (72~300 권장).",
        ),
        SecretStrInput(
            name="password",
            display_name="PDF 비밀번호 (선택)",
            value="",
            info="암호화된 PDF인 경우 입력하세요.",
        ),
    ]

    outputs = [
        Output(display_name="Markdown Result", name="result", method="search"),
        Output(display_name="Figure Paths", name="figures", method="get_figures"),
    ]

    # 인덱스 캐시 (같은 파일 재파싱 방지)
    _cached_index: Optional[PDFIndex] = None
    _cached_path: str = ""

    def _get_index(self) -> PDFIndex:
        pdf_path = str(self.pdf_file)
        if self._cached_path != pdf_path:
            self._cached_index = PDFIndex(pdf_path, self.password or None)
            self._cached_path = pdf_path
        return self._cached_index  # type: ignore[return-value]

    def search(self) -> Message:
        index = self._get_index()
        query = self.search_query

        text_chunks = (
            index.search_text_chunks(query, self.top_k, self.similarity_threshold)
            if self.search_text else []
        )
        matched_tables = (
            index.search_tables(query, self.top_k, self.similarity_threshold)
            if self.search_tables else []
        )
        matched_figures = (
            index.search_figures(query, self.top_k, self.similarity_threshold)
            if self.search_figures else []
        )

        # 그림 이미지 저장
        if self.search_figures:
            out_dir = Path(self.figure_output_dir)
            for fig in matched_figures:
                saved = save_figure_image(
                    str(self.pdf_file), fig, out_dir, dpi=int(self.figure_dpi)
                )
                fig["saved_path"] = saved

        md = format_search_results(
            query=query,
            metadata=index.metadata,
            text_chunks=text_chunks,
            tables=matched_tables,
            figures=matched_figures,
        )
        return Message(text=md)

    def get_figures(self) -> Data:
        """저장된 그림 경로 목록을 Data로 반환 (search() 이후 호출)"""
        index = self._get_index()
        query = self.search_query
        matched = (
            index.search_figures(query, self.top_k, self.similarity_threshold)
            if self.search_figures else []
        )
        out_dir = Path(self.figure_output_dir)
        paths = []
        for fig in matched:
            saved = save_figure_image(
                str(self.pdf_file), fig, out_dir, dpi=int(self.figure_dpi)
            )
            if saved:
                paths.append(saved)
        return Data(data={"figure_paths": paths, "count": len(paths)})


# ── ② 전체-JSON 변환 컴포넌트 ────────────────────────────────────────────────

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
        result = convert_pdf_to_json(
            pdf_path=self.pdf_file,
            extract_images=self.extract_images,
            extract_word_positions=self.extract_word_positions,
            password=self.password or None,
        )
        if self.output_format == "JSON 문자열":
            return Data(data={"json_string": json.dumps(result, ensure_ascii=False, indent=2)})
        return Data(data=result)


# ══════════════════════════════════════════════════════════════════════════════
# §8  CLI 단독 실행
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="PDF Knowledge Search / JSON 변환")
    sub = parser.add_subparsers(dest="cmd")

    # search 서브커맨드
    sp = sub.add_parser("search", help="쿼리와 관련된 표·그림·텍스트 검색")
    sp.add_argument("pdf_path")
    sp.add_argument("query", help="검색 쿼리")
    sp.add_argument("--top-k", type=int, default=5)
    sp.add_argument("--threshold", type=float, default=0.05)
    sp.add_argument("--figure-dir", default="./pdf_figures")
    sp.add_argument("--dpi", type=int, default=150)
    sp.add_argument("--password", default=None)
    sp.add_argument("--no-figures", action="store_true")

    # convert 서브커맨드 (기존)
    cp = sub.add_parser("convert", help="PDF 전체를 JSON으로 변환")
    cp.add_argument("pdf_path")
    cp.add_argument("--output", "-o", default=None)
    cp.add_argument("--no-images", action="store_true")
    cp.add_argument("--word-positions", action="store_true")
    cp.add_argument("--password", default=None)

    args = parser.parse_args()

    if args.cmd == "search":
        print(f"[*] PDF 인덱싱: {args.pdf_path}")
        index = PDFIndex(args.pdf_path, args.password)
        print(f"    표 {len(index.tables)}개 / 그림 {len(index.figures)}개 발견")

        chunks = index.search_text_chunks(args.query, args.top_k, args.threshold)
        tables = index.search_tables(args.query, args.top_k, args.threshold)
        figs = index.search_figures(args.query, args.top_k, args.threshold)

        if not args.no_figures:
            out_dir = Path(args.figure_dir)
            for fig in figs:
                saved = save_figure_image(args.pdf_path, fig, out_dir, args.dpi)
                fig["saved_path"] = saved
                if saved:
                    print(f"[✓] 그림 저장: {saved}")

        md = format_search_results(args.query, index.metadata, chunks, tables, figs)
        print("\n" + md)

    elif args.cmd == "convert":
        print(f"[*] PDF 변환: {args.pdf_path}")
        data = convert_pdf_to_json(
            args.pdf_path,
            extract_images=not args.no_images,
            extract_word_positions=args.word_positions,
            password=args.password,
        )
        out = args.output or str(Path(args.pdf_path).with_suffix(".json"))
        with open(out, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[✓] 완료: {out}")
        print(f"    페이지:{data['summary']['total_pages']}  "
              f"표:{data['summary']['total_tables']}  "
              f"이미지:{data['summary']['total_images']}")

    else:
        parser.print_help()
