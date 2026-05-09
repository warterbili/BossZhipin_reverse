"""示例: 过滤低薪岗位。删除此文件 / 改阈值即可。"""
import re

from pipelines import on


def parse_salary_min(s: str) -> int:
    m = re.match(r"^(\d+)\s*-\s*\d+\s*[Kk]", str(s or ""))
    return int(m.group(1)) if m else 0


@on("record", table="boss_jobs")
def drop_low_salary(record: dict):
    """薪资 < 15K 不要。"""
    if parse_salary_min(record.get("salaryDesc", "")) < 15:
        return None  # 丢弃
    return record


@on("record", table="boss_jobs")
def normalize_brand(record: dict):
    """公司名简化（去 '上海某小型XX' 字样）。"""
    brand = record.get("brandName", "")
    if "某" in brand and ("小型" in brand or "中型" in brand or "大型" in brand):
        record["brandName_normalized"] = brand
        record["brandName"] = brand.split("某")[-1] if "某" in brand else brand
    return record
