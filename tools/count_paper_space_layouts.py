import ezdxf

def main(dxf_file):
    """
    DXFファイルのペーパー空間のレイアウト数を返す（Modelは除外）。

    Args:
        dxf_file (str): DXFファイルのパス

    Returns:
        int: ペーパー空間レイアウトの数
    """
    doc = ezdxf.readfile(dxf_file)
    paper_layouts = [layout for layout in doc.layouts if layout.name.lower() != "model"]
    return len(paper_layouts)

# ----------------------------
# Entry Point
# ----------------------------
if __name__ == "__main__":
    pass