"""六单位预置 + 15所值勤报告接口清单中的共享路径与 JSON 取值规则。"""
from __future__ import annotations

DEFAULT_ORG_UNIT_REMARK = "运维、安防数据"

DEFAULT_ORG_UNITS = [
    {
        "code": "hq",
        "name": "空军本级",
        "aliases": ["空军本级", "本级"],
        "sort_order": 1,
    },
    {
        "code": "east",
        "name": "东部战区空军",
        "aliases": ["东部战区空军", "东部空军"],
        "sort_order": 2,
    },
    {
        "code": "west",
        "name": "西部战区空军",
        "aliases": ["西部战区空军", "西部空军"],
        "sort_order": 3,
    },
    {
        "code": "south",
        "name": "南部战区空军",
        "aliases": ["南部战区空军", "南部空军"],
        "sort_order": 4,
    },
    {
        "code": "north",
        "name": "北部战区空军",
        "aliases": ["北部战区空军", "北部空军"],
        "sort_order": 5,
    },
    {
        "code": "center",
        "name": "中部战区空军",
        "aliases": ["中部战区空军", "中部空军"],
        "sort_order": 6,
    },
]

# 模板表1列顺序（后两列无接口，填报时跳过）
TABLE1_COLUMN_CODES = ["hq", "east", "south", "west", "north", "center", None, None]

# 填报 / 筛选下拉用短名
UNIT_SHORT_LABELS = {
    "hq": "空军本级",
    "east": "东部",
    "west": "西部",
    "south": "南部",
    "north": "北部",
    "center": "中部",
}

DEFAULT_METRIC_SOURCES = [
    {
        "code": "construction_point",
        "name": "建设点位 / 节点数",
        "method": "GET",
        "path": "/api/index/getConstructionPoint?levelField=0",
        "sort_order": 1,
        "rules": [
            {"key": "all_counts", "label": "节点总数", "kind": "path",
             "json_paths": ["data.allCounts", "allCounts"], "fmt": "int"},
            {"key": "online_counts", "label": "在线节点数", "kind": "path",
             "json_paths": ["data.onlineCounts", "onlineCounts"], "fmt": "int"},
            {"key": "built_counts", "label": "已建节点数", "kind": "path",
             "json_paths": ["data.builtCounts", "builtCounts"], "fmt": "int"},
        ],
    },
    {
        "code": "access_network_user",
        "name": "入网用户数",
        "method": "GET",
        "path": "/api/sjyy/getSynthesizeStatisticsData/access_network_user",
        "sort_order": 2,
        "rules": [
            {"key": "access_network_user", "label": "入网用户数", "kind": "first_number",
             "json_paths": [
                 "data.number", "data.value", "data.count", "data.total",
                 "data.data", "number", "value", "count",
             ], "fmt": "int"},
        ],
    },
    {
        "code": "operation_situation",
        "name": "运行态势综合",
        "method": "GET",
        "path": "/api/sjyy/getOperationSituationSynthesizeSjyy",
        "sort_order": 3,
        "rules": [
            {"key": "node_online_rate", "label": "节点在线率", "kind": "key_field",
             "list_paths": ["data", ""], "key_field": "keyField",
             "key_values": ["node_online_quan"], "value_path": "number", "fmt": "percent"},
            {"key": "equipment_ok_rate", "label": "设备完好率", "kind": "key_field",
             "list_paths": ["data", ""], "key_field": "keyField",
             "key_values": ["equipment_ok_rate_quan"], "value_path": "number", "fmt": "percent"},
            {"key": "data_service_volume", "label": "数据服务量", "kind": "key_field",
             "list_paths": ["data", ""], "key_field": "keyField",
             "key_values": [
                 "data_service_quan", "data_svc_quan", "sjfwl",
                 "data_service", "data_service_amount",
             ], "value_path": "number", "fmt": "raw"},
        ],
    },
    {
        "code": "doc_interaction",
        "name": "文档交互量",
        "method": "GET",
        "path": "/api/sjyy/getApplicationServiceStatus/doc_interaction",
        "sort_order": 4,
        "rules": [
            {"key": "doc_interaction", "label": "文档交互量", "kind": "first_number",
             "json_paths": [
                 "data.number", "data.value", "data.count", "data.total",
                 "number", "value", "count",
             ], "fmt": "int"},
        ],
    },
    {
        "code": "storage_resource",
        "name": "计算与存储资源",
        "method": "GET",
        "path": "/bigStorageUsedInfo/getStorageResource",
        "sort_order": 5,
        "rules": [
            {"key": "js_resource_pct", "label": "计算资源使用率", "kind": "path",
             "json_paths": ["data.jsResourcePct", "jsResourcePct"], "fmt": "percent"},
            {"key": "storage_resource_pct", "label": "存储空间使用率", "kind": "path",
             "json_paths": ["data.storageResourcePct", "storageResourcePct"], "fmt": "percent"},
        ],
    },
]

CLEAN_SOURCE = "战区采集"
CLEAN_CATEGORY = "战区指标"

# 展示版预置指标（本级数字对齐 15所清单样例；其余单位做合理差异，不访问真实接口）
def _demo_item(display, value, label):
    return {"display": str(display), "metric_value": value, "label": label}


DEMO_UNIT_METRICS = {
    "hq": {
        "all_counts": _demo_item("288", 288, "节点总数"),
        "online_counts": _demo_item("216", 216, "在线节点数"),
        "built_counts": _demo_item("233", 233, "已建节点数"),
        "node_ratio": _demo_item("216/288", 216, "在线节点/节点数"),
        "node_online_rate": _demo_item("93.00%", 93.0, "节点在线率"),
        "equipment_ok_rate": _demo_item("90.00%", 90.0, "设备完好率"),
        "js_resource_pct": _demo_item("85.33%", 85.33, "计算资源使用率"),
        "storage_resource_pct": _demo_item("63.85%", 63.85, "存储空间使用率"),
        "access_network_user": _demo_item("12860", 12860, "入网用户数"),
        "data_service_volume": _demo_item("1.26万", 12600, "数据服务量"),
        "doc_interaction": _demo_item("3520", 3520, "文档交互量"),
    },
    "east": {
        "all_counts": _demo_item("256", 256, "节点总数"),
        "online_counts": _demo_item("198", 198, "在线节点数"),
        "built_counts": _demo_item("210", 210, "已建节点数"),
        "node_ratio": _demo_item("198/256", 198, "在线节点/节点数"),
        "node_online_rate": _demo_item("91.50%", 91.5, "节点在线率"),
        "equipment_ok_rate": _demo_item("88.20%", 88.2, "设备完好率"),
        "js_resource_pct": _demo_item("78.40%", 78.4, "计算资源使用率"),
        "storage_resource_pct": _demo_item("71.12%", 71.12, "存储空间使用率"),
        "access_network_user": _demo_item("9640", 9640, "入网用户数"),
        "data_service_volume": _demo_item("0.86万", 8600, "数据服务量"),
        "doc_interaction": _demo_item("2180", 2180, "文档交互量"),
    },
    "south": {
        "all_counts": _demo_item("188", 188, "节点总数"),
        "online_counts": _demo_item("142", 142, "在线节点数"),
        "built_counts": _demo_item("160", 160, "已建节点数"),
        "node_ratio": _demo_item("142/188", 142, "在线节点/节点数"),
        "node_online_rate": _demo_item("94.20%", 94.2, "节点在线率"),
        "equipment_ok_rate": _demo_item("87.50%", 87.5, "设备完好率"),
        "js_resource_pct": _demo_item("76.88%", 76.88, "计算资源使用率"),
        "storage_resource_pct": _demo_item("66.20%", 66.2, "存储空间使用率"),
        "access_network_user": _demo_item("7320", 7320, "入网用户数"),
        "data_service_volume": _demo_item("0.61万", 6100, "数据服务量"),
        "doc_interaction": _demo_item("1640", 1640, "文档交互量"),
    },
    "west": {
        "all_counts": _demo_item("210", 210, "节点总数"),
        "online_counts": _demo_item("164", 164, "在线节点数"),
        "built_counts": _demo_item("178", 178, "已建节点数"),
        "node_ratio": _demo_item("164/210", 164, "在线节点/节点数"),
        "node_online_rate": _demo_item("89.00%", 89.0, "节点在线率"),
        "equipment_ok_rate": _demo_item("92.10%", 92.1, "设备完好率"),
        "js_resource_pct": _demo_item("81.05%", 81.05, "计算资源使用率"),
        "storage_resource_pct": _demo_item("58.40%", 58.4, "存储空间使用率"),
        "access_network_user": _demo_item("8010", 8010, "入网用户数"),
        "data_service_volume": _demo_item("0.72万", 7200, "数据服务量"),
        "doc_interaction": _demo_item("1890", 1890, "文档交互量"),
    },
    "north": {
        "all_counts": _demo_item("230", 230, "节点总数"),
        "online_counts": _demo_item("176", 176, "在线节点数"),
        "built_counts": _demo_item("195", 195, "已建节点数"),
        "node_ratio": _demo_item("176/230", 176, "在线节点/节点数"),
        "node_online_rate": _demo_item("90.80%", 90.8, "节点在线率"),
        "equipment_ok_rate": _demo_item("91.00%", 91.0, "设备完好率"),
        "js_resource_pct": _demo_item("82.14%", 82.14, "计算资源使用率"),
        "storage_resource_pct": _demo_item("60.55%", 60.55, "存储空间使用率"),
        "access_network_user": _demo_item("8870", 8870, "入网用户数"),
        "data_service_volume": _demo_item("0.79万", 7900, "数据服务量"),
        "doc_interaction": _demo_item("2010", 2010, "文档交互量"),
    },
    "center": {
        "all_counts": _demo_item("201", 201, "节点总数"),
        "online_counts": _demo_item("155", 155, "在线节点数"),
        "built_counts": _demo_item("170", 170, "已建节点数"),
        "node_ratio": _demo_item("155/201", 155, "在线节点/节点数"),
        "node_online_rate": _demo_item("92.60%", 92.6, "节点在线率"),
        "equipment_ok_rate": _demo_item("89.40%", 89.4, "设备完好率"),
        "js_resource_pct": _demo_item("79.33%", 79.33, "计算资源使用率"),
        "storage_resource_pct": _demo_item("64.08%", 64.08, "存储空间使用率"),
        "access_network_user": _demo_item("6980", 6980, "入网用户数"),
        "data_service_volume": _demo_item("0.58万", 5800, "数据服务量"),
        "doc_interaction": _demo_item("1510", 1510, "文档交互量"),
    },
}


def demo_metrics_map() -> dict:
    """与 latest_metrics_map 同结构，供展示填报使用。"""
    names = {u["code"]: u["name"] for u in DEFAULT_ORG_UNITS}
    out = {}
    for code, keys in DEMO_UNIT_METRICS.items():
        inner = {}
        for key, info in keys.items():
            inner[key] = {
                "display": info["display"],
                "metric_value": info.get("metric_value"),
                "label": info.get("label") or key,
                "unit_name": names.get(code, code),
                "occur_time": None,
            }
        out[code] = inner
    return out
