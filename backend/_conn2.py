import dmPython
for u, pw in [("ZHXX_SUO_JIAN", "zhxx_suo_jian"), ("zhxx_suo_jian", "zhxx_suo_jian")]:
    try:
        c = dmPython.connect(user=u, password=pw, server="LOCALHOST", port=5236)
        cc = c.cursor(); cc.execute("SELECT USER"); print(f"  {u}/{pw}@5236 -> 成功 ({cc.fetchone()[0]})"); cc.close(); c.close()
    except Exception as e:
        print(f"  {u}/{pw}@5236 -> 失败: {repr(e)[:70]}")
