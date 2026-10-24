"""入库链路的错误分类（S1-T03）。

分类是产品契约的一部分：每类错误用户可见文案与后续动作不同，且必须与
"知识库没有答案"区分。分类口径见 docs/implementation-plan.md §5 与
backlog S1-T03 条件 2——空文本不得记为索引成功（fail-loud）。
"""
from __future__ import annotations

from typing import Any


class IngestError(Exception):
    """入库过程的可分类失败。error_class 取值如下：

    - unsupported_type:  不支持的文件类型（首期仅 Markdown/TXT/可提取文本 PDF）
    - empty_file:        空文件
    - oversized:         超出大小/页数上限（不得误报成扫描件）
    - corrupt_file:      文件损坏或解码失败
    - no_text_layer:     PDF 无可抽取文本层（扫描样），显式失败而非静默跳过
    - empty_text:        可解码但无有效文本内容（同样不得记为成功）
    """

    def __init__(self, error_class: str, detail: str, info: dict[str, Any] | None = None):
        super().__init__(f"{error_class}: {detail}")
        self.error_class = error_class
        self.detail = detail
        self.info = info or {}
