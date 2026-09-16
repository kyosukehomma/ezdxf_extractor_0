import re
from typing import List
from ezdxf.enums import TextEntityAlignment

# ----------------------------------------
# Constants
# ----------------------------------------
# MTEXT の attachment_point(1..9) を TEXT アラインメントへ概ねマッピング
_MTEXTP_TO_TEXT_ALIGN_MAP = {
    1: TextEntityAlignment.LEFT,    # TOP-LEFT
    2: TextEntityAlignment.CENTER,  # TOP-CENTER
    3: TextEntityAlignment.RIGHT,   # TOP-RIGHT
    4: TextEntityAlignment.LEFT,    # MIDDLE-LEFT
    5: TextEntityAlignment.MIDDLE,  # MIDDLE-CENTER（TEXTのMIDDLEは上下中央）
    6: TextEntityAlignment.RIGHT,   # MIDDLE-RIGHT
    7: TextEntityAlignment.LEFT,    # BOTTOM-LEFT
    8: TextEntityAlignment.CENTER,  # BOTTOM-CENTER
    9: TextEntityAlignment.RIGHT,   # BOTTOM-RIGHT
}

# TEXT の重複判定に用いる座標誤差
_TOLERANCE = 0.001

# 半角/全角スペース、TAB、改行を除去するための正規表現
_TEXT_CLEAN_PATTERN = re.compile(r"[ \u3000\t\r\n]+")


# ----------------------------------------
# Helpers
# ----------------------------------------
def mtext_attachment_to_text_align(mt) -> TextEntityAlignment:
    """
    MTEXT の `attachment_point` (1..9) を TEXT のアラインメントに概ね対応付けて返す。
    未設定または範囲外の値の場合は `TextEntityAlignment.LEFT` を返す。

    Args:
        mt: ezdxf の MTEXT エンティティ。`mt.dxf.attachment_point` を参照する。

    Returns:
        TextEntityAlignment: TEXT のアラインメント列挙子（LEFT/CENTER/RIGHT/MIDDLE 等）。

    Notes:
        - 対応表は `_MTEXTP_TO_TEXT_ALIGN_MAP` に基づく。
        - `attachment_point` が取得できない場合は 1 とみなす。
    """
    ap = int(getattr(mt.dxf, "attachment_point", 1))
    return _MTEXTP_TO_TEXT_ALIGN_MAP.get(ap, TextEntityAlignment.LEFT)


def _clean_text(raw: str) -> str:
    """
    文字列から空白類（半角/全角スペース、TAB、改行）を除去して返す。

    Args:
        raw (str): 元の文字列。`None` や空文字も許容。

    Returns:
        str: 空白類を除去した文字列。

    Notes:
        - 除去パターンは `_TEXT_CLEAN_PATTERN`（正規表現 `r"[ \u3000\t\r\n]+"`）を用いる。
    """
    return _TEXT_CLEAN_PATTERN.sub("", raw or "")


def _is_duplicate(
        x: float,
        y: float,
        cleaned: str,
        uniques: List[dict]
    ) -> bool:
    """
    TEXT の重複判定を行う。文字列が同一かつ座標 (x, y) が許容誤差内の場合 True。

    許容誤差は `_TOLERANCE`（デフォルト 0.001）。

    Args:
        x (float)           : 比較対象の X 座標。
        y (float)           : 比較対象の Y 座標。
        cleaned (str)       : 比較対象の文字列（クリーン済み）。
        uniques (List[dict]): 既にユニークと認定済みのテキスト情報リスト。
            例: `{"text": <str>, "x": <float>, "y": <float>}` の辞書。

    Returns:
        bool: 重複と判定した場合 True、そうでない場合 False。

    Notes:
        - X/Y それぞれの差が `_TOLERANCE` 以下なら「同一点」とみなす。
    """
    for t in uniques:
        if (
            t["text"] == cleaned
            and abs(t["x"] - x) <= _TOLERANCE
            and abs(t["y"] - y) <= _TOLERANCE
        ):
            return True
    return False


# ----------------------------------------
# Converters
# ----------------------------------------
def mtext_to_text_entity(
        mt,
        msp,
        preserve_alignment: bool = True
    ):
    """
    MTEXT エンティティを TEXT へ変換して Modelspace に追加し、その TEXT を返す。

    変換仕様:
        - テキスト内容は `plain_text()` があればタグ除去した文字列を使用（なければ `mt.dxf.text`）
        - `layer`, `color`, `style`, `height(char_height)`, `rotation` など主要属性を継承
        - `set_placement()` により位置とアラインメントを設定
        - 幅係数 (`width`) があれば可能な範囲で `TEXT.dxf.width` に近似反映
        - テキストが空の場合は変換せず `None` を返す

    Args:
        mt  : 変換元の MTEXT エンティティ。
        msp : 追加先の Modelspace（`doc.modelspace()`）。
        preserve_alignment (bool): MTEXT の `attachment_point` を TEXT アラインへ近似反映するか。
            False の場合は LEFT 固定。

    Returns:
        ezdxf.entities.Text | None: 生成された TEXT エンティティ。テキストが空の場合は None。

    Notes:
        - 幅係数の反映に失敗しても例外は握りつぶす（既存仕様維持）。
        - アラインメントは `mtext_attachment_to_text_align()` を用いて近似変換。
    """
    plain = (
        mt.plain_text().strip()
        if hasattr(mt, "plain_text")
        else (getattr(mt.dxf, "text", "") or "").strip()
    )
    if not plain:
        return None

    dxfattribs = {
        "layer": mt.dxf.layer,
        "color": mt.dxf.color,
        "style": mt.dxf.style,
        "height": float(getattr(mt.dxf, "char_height", 2.5) or 2.5),
        "rotation": float(getattr(mt.dxf, "rotation", 0.0) or 0.0),
    }
    new_text = msp.add_text(plain, dxfattribs=dxfattribs)

    align = mtext_attachment_to_text_align(mt) if preserve_alignment else TextEntityAlignment.LEFT
    p1 = mt.dxf.insert
    new_text.set_placement(p1=p1, align=align)

    # 幅係数（存在すれば近似的に反映）
    width_factor = getattr(mt.dxf, "width", None)
    if width_factor is not None:
        try:
            new_text.dxf.width = float(width_factor)
        except Exception:
            # 反映失敗は無視
            pass

    return new_text


def convert_all_mtext_to_text(
        doc,
        delete_original_mtext: bool = True,
        preserve_alignment: bool = True
    ):
    """
    ドキュメント中の全 MTEXT を TEXT に変換するユーティリティ。
    `delete_original_mtext=True` の場合、変換後に元 MTEXT を削除する。

    Args:
        doc: ezdxf の `Drawing`（DXF ドキュメント）。
        delete_original_mtext (bool): 変換後に MTEXT を削除するか。デフォルト True。
        preserve_alignment (bool)   : MTEXT のアラインメントを TEXT に近似反映するか。デフォルト True。

    Returns:
        List[ezdxf.entities.Text]: 生成された TEXT エンティティのリスト。

    Notes:
        - ループ中の削除安全性のため、`list(msp.query("MTEXT"))` でクエリ結果をコピーしてから処理する。
    """

    msp = doc.modelspace()
    created = []

    # list() でクエリ結果をコピーして、ループ中の削除を安全に
    for mt in list(msp.query("MTEXT")):
        t = mtext_to_text_entity(mt, msp, preserve_alignment)
        if t is not None:
            created.append(t)
        if delete_original_mtext:
            msp.delete_entity(mt)

    return created


# ----------------------------------------
# Main
# ----------------------------------------
def main(doc):
    """
    ドキュメント内のテキスト統合処理を行う。
        1) 全 MTEXT を TEXT に変換（`convert_all_mtext_to_text`）
        2) TEXT の内容をクリーンアップ（半角/全角スペース、TAB、改行の除去）
        3) 位置＆テキストが同一の TEXT を重複として削除（許容誤差 `_TOLERANCE`）

    Args:
        doc: ezdxf の `Drawing`（DXF ドキュメント）。

    Returns:
        ezdxf.drawing.Drawing: 変換と重複排除を実施した後のドキュメント。

    Notes:
        - 重複判定は主基準点（`TEXT.dxf.insert`）の (x, y) を使用。
        - クリーンアップは `_clean_text()` により空白類を除去してから比較する。
        - ループ中削除安全性のため `list(msp.query("TEXT"))` を用いる。
    """
    msp = doc.modelspace()

    # MTEXT -> TEXT
    convert_all_mtext_to_text(doc, delete_original_mtext=True, preserve_alignment=True)

    unique_texts = []

    # TEXT エンティティの内容をクリーンアップし、重複排除
    for ent in list(msp.query("TEXT")):  # list() でコピーして安全に削除可能に
        raw_text = getattr(ent.dxf, "text", "") or ""
        cleaned = _clean_text(raw_text)
        ent.dxf.text = cleaned

        # 主基準点（insert）から座標取得（既存仕様維持）
        x, y = ent.dxf.insert[0], ent.dxf.insert[1]

        if not _is_duplicate(x, y, cleaned, unique_texts):
            unique_texts.append({"text": cleaned, "x": x, "y": y})
        else:
            # 重複なら削除
            msp.delete_entity(ent)

    return doc


# ----------------------------
# Entry Point
# ----------------------------
if __name__ == "__main__":
    pass