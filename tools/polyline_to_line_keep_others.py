from typing import List, Optional

def main(
        doc,
        exclude_layers: Optional[List[str]] = None
    ):
    """
    ドキュメント内の LWPOLYLINE を LINE に分解し、その他のエンティティは操作・削除しない。

    仕様:
        - 各 LWPOLYLINE の頂点列から、隣接する頂点間を結ぶ LINE を順次生成する。
        - 閉じたポリライン（`polyline.closed`）は、最後の頂点と最初の頂点も結ぶ。
        - 生成される LINE には、元のポリラインの主要属性（`layer`, `color`, `linetype`）を継承。
        - 分解対象外レイヤー（`exclude_layers`）に属するポリラインはスキップする。
        - 変換後、元の LWPOLYLINE は削除する。

    Args:
        doc: ezdxf のドキュメント（`Drawing`）。`doc.modelspace()` を使用して処理します。
        exclude_layers (Optional[List[str]]): 分解を除外するレイヤー名のリスト。
            例: `["D-TTL-BAND"]`。未指定または空の場合は全レイヤーを対象。

    Returns:
        ezdxf.drawing.Drawing: 変換（LINE追加）と削除（LWPOLYLINE削除）を反映済みのドキュメント。

    Notes:
        - 可変デフォルト引数の副作用回避のため、内部で `exclude_layers or []` を `set` に変換して使用。
        - `msp.query("LWPOLYLINE")` の結果を `list(...)` によりコピーし、ループ中の削除を安全化。
        - 閉じたポリラインは明示的に「最後→最初」を結ぶ処理を追加。
            - `get_points()` は閉じたポリラインでも最初の頂点を最後に重複返却しないため。
        - ハンドル（`handle`）等の識別属性は継承しない。
    """

    msp = doc.modelspace()

    # 可変デフォルト引数の回避 ＆ 検索高速化のため set に変換
    exclude_set = set(exclude_layers or [])

    # polyline を line へ変換（削除と併用する場合は list() で安全に）
    for polyline in list(msp.query("LWPOLYLINE")):
        if polyline.dxf.layer in exclude_set:
            continue

        # 頂点座標 (x, y) のみ抽出
        points = [(pt[0], pt[1]) for pt in polyline.get_points()]

        # 付与する属性（handle は付与しない：元の仕様に合わせる）
        attribs = {
            "layer": polyline.dxf.layer,
            "color": polyline.dxf.color,
            "linetype": polyline.dxf.linetype,
        }

        # 各連続する点のペアに対して LINE を作成
        # get_points() は閉じたポリラインでも最初の点を最後に重複して返さない仕様
        # なので、閉じた場合は明示的に最後と最初を結ぶ
        for i in range(len(points) - 1):
            msp.add_line(points[i], points[i + 1], dxfattribs=attribs)

        if polyline.closed and len(points) >= 2:
            msp.add_line(points[-1], points[0], dxfattribs=attribs)

        # 元の polyline を削除
        msp.delete_entity(polyline)

    return doc


# ----------------------------
# Entry Point
# ----------------------------
if __name__ == "__main__":
    pass