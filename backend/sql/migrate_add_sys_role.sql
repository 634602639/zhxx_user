-- RBAC：角色表 sys_role + sys_user.role_id 列
-- 说明：应用启动时 app.py 的 _ensure_role_store() 会自动建表 / 补列 / 种子超级管理员角色，
--       两种后端都无需手工执行本脚本；此文件仅作结构留档与手工核对用。
--
-- 角色拥有一组权限点（perms，JSON 数组，如 ["collect:view","manage:edit"]）；
-- 超级管理员存 ["*"]（通配，拥有全部权限，不可改 / 不可删）。用户挂到角色上继承其权限。

-- ============ PostgreSQL ============
CREATE TABLE IF NOT EXISTS sys_role (
    id            SERIAL PRIMARY KEY,
    name          VARCHAR(64)  NOT NULL UNIQUE,   -- 显示名，如「值班员」
    code          VARCHAR(64)  NOT NULL UNIQUE,   -- 角色标识，如「operator」
    description   VARCHAR(255),
    perms         TEXT,                            -- JSON 数组：权限点编码
    is_builtin    BOOLEAN DEFAULT FALSE,           -- 内置角色不可删除
    created_at    TIMESTAMP,
    updated_at    TIMESTAMP
);

ALTER TABLE sys_user ADD COLUMN IF NOT EXISTS role_id INTEGER;  -- 用户挂载的角色（单角色）

-- 内置超级管理员角色（若不存在则插入），并把 admin 挂上去
INSERT INTO sys_role (name, code, description, perms, is_builtin, created_at, updated_at)
SELECT '超级管理员', 'super_admin', '系统内置，拥有全部权限，不可修改 / 删除', '["*"]', TRUE, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM sys_role WHERE code = 'super_admin');

UPDATE sys_user
   SET role_id = (SELECT id FROM sys_role WHERE code = 'super_admin')
 WHERE username = 'admin' AND role_id IS NULL;


-- ============ 达梦 DM8（ZHXX_SUO_JIAN schema；VARCHAR 按字节计长，已 ×3 容纳中文） ============
-- CREATE TABLE ZHXX_SUO_JIAN.SYS_ROLE (
--     id          INT IDENTITY(1,1) PRIMARY KEY,
--     name        VARCHAR(192) NOT NULL UNIQUE,
--     code        VARCHAR(192) NOT NULL UNIQUE,
--     description VARCHAR(765),
--     perms       CLOB,
--     is_builtin  BIT DEFAULT 0,
--     created_at  TIMESTAMP,
--     updated_at  TIMESTAMP
-- );
-- ALTER TABLE ZHXX_SUO_JIAN.SYS_USER ADD role_id INT;
-- INSERT INTO ZHXX_SUO_JIAN.SYS_ROLE (name, code, description, perms, is_builtin, created_at, updated_at)
--   VALUES ('超级管理员', 'super_admin', '系统内置，拥有全部权限，不可修改 / 删除', '["*"]', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
-- UPDATE ZHXX_SUO_JIAN.SYS_USER SET role_id =
--   (SELECT id FROM ZHXX_SUO_JIAN.SYS_ROLE WHERE code='super_admin') WHERE username='admin' AND role_id IS NULL;
