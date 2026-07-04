"""
②a EOM Log Sampler - Langflow 1.9.1 Custom Component

전체 로그를 LLM에 넣지 않고, 패턴 식별에 필요한 대표 샘플만 추출한다.
(하이브리드 방식: LLM은 키워드/정규식 패턴만 식별, 숫자 추출은 Python)

샘플 구성: 앞부분 head_lines줄 + 중간 5줄 + 끝 5줄
"""
from pathlib import Path

from langflow.custom import Component
from langflow.io import IntInput, MessageTextInput, Output
from langflow.schema.message import Message


def sample_log(text: str, head_lines: int = 60) -> str:
    lines = text.splitlines()
    if len(lines) <= head_lines + 10:
        return text
    mid = len(lines) // 2
    parts = (
        lines[:head_lines]
        + ["... (중략) ..."]
        + lines[mid : mid + 5]
        + ["... (중략) ..."]
        + lines[-5:]
    )
    return "\n".join(parts)


def read_text_any_encoding(path: str) -> str:
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


class EOMLogSampler(Component):
    display_name = "EOM Log Sampler"
    description = "EOM log에서 LLM 패턴 식별용 샘플 추출"
    icon = "scissors"
    name = "EOMLogSampler"

    inputs = [
        MessageTextInput(
            name="file_path",
            display_name="EOM Log File Path",
            info="storage/uploads/... (Frontend가 tweaks로 전달)",
        ),
        IntInput(
            name="head_lines",
            display_name="Head Lines",
            value=60,
            info="샘플에 포함할 앞부분 줄 수",
        ),
    ]

    outputs = [
        Output(display_name="Log Sample", name="log_sample", method="get_sample"),
    ]

    def get_sample(self) -> Message:
        text = read_text_any_encoding(self.file_path)
        sample = sample_log(text, self.head_lines or 60)
        self.status = f"sample: {len(sample)} chars / total: {len(text)} chars"
        return Message(text=sample)
