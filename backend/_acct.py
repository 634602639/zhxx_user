import dmPython

for port in (5236, 5237):
    print(f"===== {port} =====")
    c = dmPython.connect(user="SYSDBA", password="123456789", server="LOCALHOST", port=port)
    cur = c.cursor()
    try:
        cur.execute("""SELECT USERNAME, ACCOUNT_STATUS, LOCK_DATE, EXPIRY_DATE
                       FROM DBA_USERS WHERE USERNAME LIKE 'ZHXX%' ORDER BY USERNAME""")
        for r in cur.fetchall():
            print(f"  {r[0]}: 状态={r[1]} 锁定日期={r[2]} 过期日期={r[3]}")
    except Exception as e:
        print("  查 DBA_USERS 失败:", str(e)[:80])
    cur.close(); c.close()
