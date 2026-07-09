-- duty_report：移除未使用的 summary、related_systems

ALTER TABLE duty_report DROP COLUMN IF EXISTS summary;
ALTER TABLE duty_report DROP COLUMN IF EXISTS related_systems;
