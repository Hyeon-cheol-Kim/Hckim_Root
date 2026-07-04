"""
① EOM Log Loader - Langflow 1.9.1 Custom Component (신규, 재구성)

업로드된 EOM test log 파일을 읽어 인코딩을 자동 감지하고
전체 원문 텍스트(Message)를 출력한다.

재구성 의도:
  기존에는 Log Sampler와 JSON Builder가 각각 파일을 직접 읽었다.
  파일 읽기(I/O)를 단일 책임 컴포넌트로 분리하여
    Loader(log_text) ─▶ Sampler        (LLM 패턴 식별용 샘플)
                     └─▶ JSON Builder   (전체 로그 숫자 추출)
  으로 명시적으로 연결한다. (파일 이중 읽기 제거, chaining 명확화)

출력:
  - log_text : 디코딩된 전체 로그 원문 (Message)
"""
from pathlib import Path


def read_text_any_encoding(path: str) -> str:
    """UTF-8 우선, 실패 시 chardet 감지(미설치 시 cp949)로 디코딩."""
    raw = Path(path).read_bytes()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            import chardet

            enc = chardet.detect(raw)["encoding"] or "cp949"
        except ImportError:
            enc = "cp949"
        return raw.decode(enc, errors="replace")


# ---------------------------------------------------------------
# Langflow 컴포넌트부
# ---------------------------------------------------------------
from langflow.custom import Component
from langflow.io import MessageTextInput, Output
from langflow.schema.message import Message


class EOMLogLoader(Component):
    display_name = "EOM Log Loader"
    description = "EOM log 파일을 읽어 인코딩 자동 감지 후 전체 원문 텍스트를 출력"
    icon = "file-text"
    name = "EOMLogLoader"

    inputs = [
        MessageTextInput(
            name="file_path",
            display_name="EOM Log File Path",
            info="Frontend가 tweaks로 전달 (storage/uploads/...)",
        ),
    ]

    outputs = [
        Output(display_name="Log Text", name="log_text", method="load"),
    ]

    def load(self) -> Message:
        text = read_text_any_encoding(self.file_path)
        self.status = (
            f"{Path(self.file_path).name}: {len(text)} chars, "
            f"{text.count(chr(10)) + 1} lines"
        )
        return Message(text=text)
