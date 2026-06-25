"""
Langflow Custom Component: PDF to JSON Converter
PDF 파일에서 텍스트, 표(table), 그림(image) 데이터를 추출하여 JSON으로 변환
"""

import json
import base64
import io
import re
from pathlib import Path
from typing import Optional

import pdfplumber

# Langflow imports (Langflow 환경에서 실행 시 사용)
try:
    from langflow.custom import CustomComponent
    from langflow.schema import Data
    LANGFLOW_AVAILABLE = True
except ImportError:
    LANGFLOW_AVAILABLE = False


# ─────────────────────────────────────────────
# 핵심 추출 로직 (Langflow 외부에서도 재사용 가능)
# ─────────────────────────────────────────────

def _extract_tables(page) -> list[dict]:
    """pdfplumber 페이지에서 표를 추출하여 구조화된 dict 리스트 반환"""
    results = []
    tables = page.extract_tables()
    for t_idx, raw_table in enumerate(tables):
        if not raw_table:
            continue

        # 첫 행을 헤더로 사용 (None 셀은 빈 문자열로 치환)
        header = [str(cell).strip() if cell is not None else "" for cell in raw_table[0]]
        rows = []
        for raw_row in raw_table[1:]:
            row = {header[c]: (str(cell).strip() if cell is not None else "")
                   for c, cell in enumerate(raw_row)}
            rows.append(row)

        # 표의 바운딩박스 (없으면 None)
        bbox = None
        try:
            tbbox = page.find_tables()[t_idx].bbox
            bbox = {"x0": tbbox[0], "y0": tbbox[1], "x1": tbbox[2], "y1": tbbox[3]}
        except Exception:
            pass

        results.append({
            "table_index": t_idx,
            "bbox": bbox,
            "headers": header,
            "rows": rows,
            "row_count": len(rows),
            "col_count": len(header),
        })
    return results


def _extract_images(page) -> list[dict]:
    """
    pdfplumber 페이지에서 이미지(그림) 메타데이터 및 base64 데이터 추출.
    pdfplumber는 이미지 픽셀 데이터를 직접 노출하지 않으므로
    PIL(Pillow) 또는 PyMuPDF(fitz)가 있으면 래스터 이미지를 추출하고,
    없으면 메타데이터만 반환합니다.
    """
    results = []
    for img_idx, img_obj in enumerate(page.images):
        entry = {
            "image_index": img_idx,
            "name": img_obj.get("name", ""),
            "width": img_obj.get("width"),
            "height": img_obj.get("height"),
            "x0": img_obj.get("x0"),
            "y0": img_obj.get("y0"),
            "x1": img_obj.get("x1"),
            "y1": img_obj.get("y1"),
            "colorspace": img_obj.get("colorspace"),
            "bits_per_component": img_obj.get("bits"),
            "image_base64": None,
            "image_format": None,
        }

        # Pillow로 이미지 픽셀 데이터 추출 시도
        try:
            from PIL import Image as PILImage

            raw_data = img_obj.get("stream")
            if raw_data is not None:
                stream_bytes = raw_data.get_data() if hasattr(raw_data, "get_data") else bytes(raw_data)
                pil_img = PILImage.open(io.BytesIO(stream_bytes))
                buf = io.BytesIO()
                fmt = pil_img.format or "PNG"
                pil_img.save(buf, format=fmt)
                entry["image_base64"] = base64.b64encode(buf.getvalue()).decode("utf-8")
                entry["image_format"] = fmt.lower()
        except Exception:
            pass  # Pillow 없거나 스트림 접근 불가 시 메타데이터만 유지

        results.append(entry)
    return results


def _clean_text(text: str) -> str:
    """연속 공백·불필요한 줄바꿈 정리"""
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _extract_words_with_position(page) -> list[dict]:
    """단어별 위치 정보를 포함한 텍스트 추출 (표 영역 제외)"""
    try:
        table_bboxes = [t.bbox for t in page.find_tables()]
    except Exception:
        table_bboxes = []

    def _in_table(word_bbox):
        x0, y0, x1, y1 = word_bbox
        for tb in table_bboxes:
            if x0 >= tb[0] and y0 >= tb[1] and x1 <= tb[2] and y1 <= tb[3]:
                return True
        return False

    words = []
    for w in page.extract_words(x_tolerance=3, y_tolerance=3):
        if not _in_table((w["x0"], w["top"], w["x1"], w["bottom"])):
            words.append({
                "text": w["text"],
                "x0": w["x0"],
                "y0": w["top"],
                "x1": w["x1"],
                "y1": w["bottom"],
            })
    return words


def convert_pdf_to_json(
    pdf_path: str,
    extract_images: bool = True,
    extract_word_positions: bool = False,
    password: Optional[str] = None,
) -> dict:
    """
    PDF 파일을 읽어 텍스트·표·이미지 데이터를 JSON 직렬화 가능한 dict로 반환.

    Parameters
    ----------
    pdf_path : str
        PDF 파일 경로
    extract_images : bool
        그림(이미지) 메타데이터 추출 여부 (기본 True)
    extract_word_positions : bool
        단어 위치 정보 포함 여부 (기본 False, 활성화 시 출력이 매우 커짐)
    password : str | None
        암호화된 PDF 비밀번호

    Returns
    -------
    dict
        {
            "metadata": {...},
            "pages": [
                {
                    "page_number": 1,
                    "width": ...,
                    "height": ...,
                    "text": "...",
                    "tables": [...],
                    "images": [...],
                    "words": [...]   # extract_word_positions=True 시
                },
                ...
            ],
            "summary": {
                "total_pages": ...,
                "total_tables": ...,
                "total_images": ...
            }
        }
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {pdf_path}")

    open_kwargs = {"password": password} if password else {}

    with pdfplumber.open(pdf_path, **open_kwargs) as pdf:
        # ── 메타데이터 ──────────────────────────────────
        raw_meta = pdf.metadata or {}
        metadata = {
            "file_name": pdf_path.name,
            "file_size_bytes": pdf_path.stat().st_size,
            "total_pages": len(pdf.pages),
            "title": raw_meta.get("Title", ""),
            "author": raw_meta.get("Author", ""),
            "subject": raw_meta.get("Subject", ""),
            "creator": raw_meta.get("Creator", ""),
            "producer": raw_meta.get("Producer", ""),
            "creation_date": str(raw_meta.get("CreationDate", "")),
            "modification_date": str(raw_meta.get("ModDate", "")),
        }

        pages_data = []
        total_tables = 0
        total_images = 0

        for page in pdf.pages:
            page_num = page.page_number  # 1-based

            # ── 텍스트 (표 영역 제외) ─────────────────────
            raw_text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
            cleaned_text = _clean_text(raw_text)

            # ── 표 ────────────────────────────────────────
            tables = _extract_tables(page)
            total_tables += len(tables)

            # ── 이미지 ────────────────────────────────────
            images = _extract_images(page) if extract_images else []
            total_images += len(images)

            # ── 단어 위치 ─────────────────────────────────
            words = _extract_words_with_position(page) if extract_word_positions else []

            page_entry = {
                "page_number": page_num,
                "width": page.width,
                "height": page.height,
                "text": cleaned_text,
                "tables": tables,
                "images": images,
            }
            if extract_word_positions:
                page_entry["words"] = words

            pages_data.append(page_entry)

    result = {
        "metadata": metadata,
        "pages": pages_data,
        "summary": {
            "total_pages": metadata["total_pages"],
            "total_tables": total_tables,
            "total_images": total_images,
        },
    }
    return result


# ─────────────────────────────────────────────
# Langflow 커스텀 컴포넌트
# ─────────────────────────────────────────────

if LANGFLOW_AVAILABLE:
    from langflow.inputs import (
        FileInput,
        BoolInput,
        SecretStrInput,
        StrInput,
        DropdownInput,
    )
    from langflow.template import Output

    class PDFToJsonComponent(CustomComponent):
        """PDF 파일을 읽어 텍스트·표·이미지를 JSON으로 변환하는 Langflow 컴포넌트"""

        display_name = "PDF to JSON Converter"
        description = (
            "PDF 파일에서 텍스트, 표(table), 그림(image) 데이터를 추출하여 "
            "구조화된 JSON Data로 변환합니다."
        )
        icon = "file-text"
        name = "PDFToJsonConverter"

        inputs = [
            FileInput(
                name="pdf_file",
                display_name="PDF 파일",
                file_types=["pdf"],
                required=True,
                info="변환할 PDF 파일을 업로드하세요.",
            ),
            BoolInput(
                name="extract_images",
                display_name="이미지 추출",
                value=True,
                info="PDF 내 그림/이미지 메타데이터를 추출합니다.",
            ),
            BoolInput(
                name="extract_word_positions",
                display_name="단어 위치 정보 포함",
                value=False,
                info="각 단어의 좌표 정보를 포함합니다 (출력 크기가 크게 증가합니다).",
            ),
            DropdownInput(
                name="output_format",
                display_name="출력 형식",
                options=["Data (구조화)", "JSON 문자열"],
                value="Data (구조화)",
                info="출력 타입을 선택합니다.",
            ),
            SecretStrInput(
                name="password",
                display_name="PDF 비밀번호 (선택)",
                value="",
                info="암호화된 PDF인 경우 비밀번호를 입력하세요.",
            ),
        ]

        outputs = [
            Output(display_name="JSON Data", name="json_data", method="convert"),
        ]

        def convert(self) -> Data:
            pdf_path = self.pdf_file  # Langflow가 임시 경로 문자열을 전달

            result_dict = convert_pdf_to_json(
                pdf_path=pdf_path,
                extract_images=self.extract_images,
                extract_word_positions=self.extract_word_positions,
                password=self.password or None,
            )

            if self.output_format == "JSON 문자열":
                return Data(data={"json_string": json.dumps(result_dict, ensure_ascii=False, indent=2)})

            # 기본: 구조화된 Data 반환
            return Data(data=result_dict)


# ─────────────────────────────────────────────
# 단독 실행 (python pdf_to_json_langflow.py <파일.pdf>)
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="PDF → JSON 변환기")
    parser.add_argument("pdf_path", help="변환할 PDF 파일 경로")
    parser.add_argument("--output", "-o", default=None, help="출력 JSON 파일 경로 (기본: <pdf명>.json)")
    parser.add_argument("--no-images", action="store_true", help="이미지 추출 건너뜀")
    parser.add_argument("--word-positions", action="store_true", help="단어 위치 정보 포함")
    parser.add_argument("--password", default=None, help="암호화된 PDF 비밀번호")
    parser.add_argument("--pretty", action="store_true", default=True, help="보기 좋은 JSON 출력")
    args = parser.parse_args()

    print(f"[*] PDF 변환 시작: {args.pdf_path}")

    data = convert_pdf_to_json(
        pdf_path=args.pdf_path,
        extract_images=not args.no_images,
        extract_word_positions=args.word_positions,
        password=args.password,
    )

    out_path = args.output or Path(args.pdf_path).with_suffix(".json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2 if args.pretty else None)

    print(f"[✓] 완료: {out_path}")
    print(f"    총 페이지:  {data['summary']['total_pages']}")
    print(f"    총 표 수:   {data['summary']['total_tables']}")
    print(f"    총 이미지:  {data['summary']['total_images']}")
