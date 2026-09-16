import re
from typing import Any, List, Optional, Tuple
from tools.belt_utils import get_belt_y_positions, get_texts_in_range
from tools.controller import SUPERELEVATION_TITLE_CANDIDATES

def _process_texts_fraction(
        texts_in_range: List[Tuple[str, Tuple[float, float], float]]
) -> Optional[List[Tuple[float, Tuple[float, float], str]]]:
    """
    分数表記（`"/"` を含む、例: `3/4`, `-2/5`）を抽出し、(値, 座標, 原文) のリストを返す。
        - 正規表現 `([+-]?)\\s*(\\d+)\\s*/\\s*(\\d+)` に一致する最初の分数を抽出。
        - `-` の符号に対応（先頭符号のみ）。空白は無視。
        - 値は `a / b`（float）で算出。
        - 分母が 0 の場合は処理を中断し `None` を返す（既存仕様踏襲）。

    Args:
        texts_in_range (List[Tuple[str, Tuple[float, float], float]]):
            `(text, (x, y), rotation_deg)` のタプルのリスト。

    Returns:
        Optional[List[Tuple[float, Tuple[float, float], str]]]:
            成功時: `[(value: float, position: (x, y), original_text: str), ...]`
            - 該当が無い場合は空リスト `[]`
            - 分母 0 を検出した場合は `None`

    Notes:
        - テキスト中に `"/"` が含まれる場合のみ正規表現を適用（簡易高速化）。
        - 最初に一致した分数のみを対象とし、同一テキスト中の複数分数は考慮しない既存仕様。
    """

    RE_FRAC = re.compile(r'([+-]?)\s*(\d+)\s*/\s*(\d+)')
    processed: List[Tuple[float, Tuple[float, float], str]] = []
    for text, position, _ in texts_in_range:
        if "/" in text:
            m = RE_FRAC.search(text)
            if m:
                sign, a_str, b_str = m.groups()
                a = int(a_str)
                b = int(b_str)
                if b == 0:
                    return None
                val = a / b
                if sign == "-":
                    val = -val
                processed.append((val, position, text))
    return processed


def main(msp: Any, layer: str):
    """
    片勾配すり付け図の帯内に記載された分数（●/●）のうち、最大値に対応する原テキストを抽出して返す。
        1) 帯タイトルの候補（`label, c1, c2`）を順番に試行し、最初に検出した帯の上下端 (min_y, max_y) を採用。
        2) 採用した帯範囲内の TEXT を抽出（`get_texts_in_range`）。
        3) 分数表記を抽出（`_process_texts_fraction`）。分母 0 を検出した場合は `None` を返す。
        4) 抽出された分数のうち、数値の最大値に一致する**元のテキスト文字列**を返す。

    失敗時の挙動:
        - 帯が検出できない場合: `"-"`
        - 分数が 1 件も抽出できない場合: `"-"`
        - 分母 0 の分数を検出した場合: `None`（既存仕様に従う）

    Args:
        msp (Any): ezdxf の Modelspace。
        layer (str): タイトルや分数が配置されている帯レイヤー名。

    Returns:
        str | None:
            - 成功時: 最大値に一致する原テキスト（例: `"3/4"`）。
            - 失敗時: `"-"`。
            - 分母 0 を検出した場合: `None`。

    Notes:
        - 帯タイトルの候補は以下の順に試行します:
            1) `"片勾配すり付け図"`（分割: `"片"` / `"図"`）
            2) `"片勾配すり付図"`（分割: `"片"` / `"配"`）
            3) `"片勾配"`（分割: `"片"` / `"配"`）
        - `find_belt_edges_by_text.main()` による帯推定の仕様に依存します。
        - 最大値に一致する**最初に見つかった原テキスト**を返す既存ロジックを維持しています。
    """

    # 探索候補
    candidates = SUPERELEVATION_TITLE_CANDIDATES

    # 帯の上端・下端 を探索（最初に見つかったものを採用）
    min_y = max_y = None
    for label, c1, c2 in candidates:
        min_y, max_y = get_belt_y_positions(msp, layer, label, c1, c2)
        if min_y is not None and max_y is not None:
            break

    # 帯が見つからない場合は安全に早期終了（曲率コードの方針に合わせる）
    if min_y is None or max_y is None:
        return "-"

    # 範囲内 TEXT を取得
    texts_in_range = get_texts_in_range(msp, layer, min_y, max_y)

    # 分数抽出（既存仕様：分母 0 で None）
    target_texts = _process_texts_fraction(texts_in_range)
    if target_texts is None:
        return None  # 既存仕様踏襲（呼び出し側での扱いに応じて "-" にしたければ変更可）
    if not target_texts:
        return "-"

    # 最大値に一致する原テキストを返す（既存ロジック維持）
    max_val = max(val for val, _, _ in target_texts)
    for val, _, original_text in target_texts:
        if val == max_val:
            return original_text

    # 理論上到達しないが、保険でフォールバック
    return "-"