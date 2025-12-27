import json
import os
import shutil
import time
from typing import Dict, Optional, Tuple, List
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api.event import filter
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot import logger

@register("astrbot_plugin_preset_hub", "Antigravity", "全局预设中心", "2.1.1")
class PresetHub(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        
        # 路径配置
        self.data_dir = StarTools.get_data_dir("astrbot_plugin_preset_hub")
        self.preset_file = os.path.join(str(self.data_dir), "global_presets.json")
        self.backup_file = os.path.join(str(self.data_dir), "global_presets.json.bak")
        
        # 内存数据结构
        self.data = {
            "presets": {},
            "aliases": {}
        }
        
        # 1. 加载本地数据
        self._load_data()
        
        # 2. 从 WebUI 配置同步数据
        self._sync_webui_config()

    def _sync_webui_config(self):
        """从 WebUI 的 prompt_list 同步预设"""
        prompt_list = self.config.get("prompt_list", [])
        if not prompt_list:
            return

        updated = False
        for item in prompt_list:
            if ":" in item:
                key, value = item.split(":", 1)
                key = key.strip()
                value = value.strip()
                
                if key and value:
                    if self.data["presets"].get(key) != value:
                        self.data["presets"][key] = value
                        updated = True
                        logger.info(f"[PresetHub] 从配置同步预设: {key}")
        
        if updated:
            self._save_safe()

    def _load_data(self):
        """加载数据"""
        if not os.path.exists(self.preset_file):
            self._init_default_data()
            return
        
        try:
            with open(self.preset_file, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            
            if "presets" in raw and isinstance(raw["presets"], dict):
                self.data = raw
                if "aliases" not in self.data:
                    self.data["aliases"] = {}
                logger.info(f"[PresetHub] 已加载 {len(self.data['presets'])} 个预设")
            else:
                # 兼容旧版数据迁移
                logger.warning("[PresetHub] 迁移旧版数据...")
                migrated = {}
                for k, v in raw.items():
                    if isinstance(v, dict) and "prompt" in v:
                        migrated[k] = str(v["prompt"])
                    else:
                        migrated[k] = str(v)
                self.data = {"presets": migrated, "aliases": {}}
                self._save_safe()

        except Exception as e:
            logger.error(f"[PresetHub] 加载失败: {e}")
            self._init_default_data()

    def _init_default_data(self):
        """初始化默认数据 (已清空默认库)"""
        # 这里不再写入默认的手办/二次元等预设，保持纯净
        self.data = {
            "presets": {},
            "aliases": {}
        }
        self._save_safe()

    def _save_safe(self) -> bool:
        os.makedirs(os.path.dirname(self.preset_file), exist_ok=True)
        try:
            if os.path.exists(self.preset_file):
                shutil.copy(self.preset_file, self.backup_file)
            
            with open(self.preset_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"[PresetHub] 保存失败: {e}")
            return False

    def resolve_preset(self, key: str) -> Optional[str]:
        if not key: return None
        real_key = self.data["aliases"].get(key, key)
        return self.data["presets"].get(real_key)

    def get_all_keys(self) -> List[str]:
        return list(self.data["presets"].keys()) + list(self.data["aliases"].keys())

    # ================= 交互指令 =================

    @filter.command("添加预设")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def add_preset(self, event: AstrMessageEvent, key: str = None, *, value: str = None):
        raw_msg = event.message_str.strip()
        parts = raw_msg.split(maxsplit=2)
        
        if len(parts) < 3:
             yield event.plain_result("❌ 用法: /添加预设 关键词 提示词内容")
             return

        target_key = parts[1]
        prompt_content = parts[2].strip()

        if target_key in self.data["aliases"]:
            del self.data["aliases"][target_key]

        self.data["presets"][target_key] = prompt_content
        
        if self._save_safe():
            preview = prompt_content[:20] + "..." if len(prompt_content) > 20 else prompt_content
            yield event.plain_result(f"✅ 预设 [{target_key}] 已保存。")
        else:
            yield event.plain_result("❌ 保存失败。")

    @filter.command("预设别名")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def add_alias(self, event: AstrMessageEvent, source: str, alias: str):
        if source not in self.data["presets"]:
            yield event.plain_result(f"❌ 原预设 [{source}] 不存在。")
            return
        if alias in self.data["presets"]:
            yield event.plain_result(f"❌ [{alias}] 也是主预设，无法设为别名。")
            return
        self.data["aliases"][alias] = source
        self._save_safe()
        yield event.plain_result(f"🔗 已关联: [{alias}] -> [{source}]")

    @filter.command("删除预设")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def del_preset(self, event: AstrMessageEvent, key: str):
        if key in self.data["aliases"]:
            real = self.data["aliases"][key]
            del self.data["aliases"][key]
            self._save_safe()
            yield event.plain_result(f"🗑️ 别名 [{key}] 已删除。")
            return
        if key in self.data["presets"]:
            del self.data["presets"][key]
            to_remove = [k for k, v in self.data["aliases"].items() if v == key]
            for k in to_remove:
                del self.data["aliases"][k]
            self._save_safe()
            yield event.plain_result(f"🗑️ 主预设 [{key}] 已删除。")
            return
        yield event.plain_result(f"❌ 未找到: [{key}]")

    @filter.command("预设列表")
    async def list_presets(self, event: AstrMessageEvent):
        if not self.data["presets"]:
            yield event.plain_result("📭 当前预设库为空。")
            return

        reverse_aliases = {}
        for alias, real in self.data["aliases"].items():
            if real not in reverse_aliases:
                reverse_aliases[real] = []
            reverse_aliases[real].append(alias)

        lines = [f"🌏 全局预设库 ({len(self.data['presets'])}):", "━" * 20]
        for k, v in self.data["presets"].items():
            alias_str = ""
            if k in reverse_aliases:
                alias_str = f" (🔗{','.join(reverse_aliases[k])})"
            preview = v[:20].replace("\n", " ") + "..." if len(v) > 20 else v
            lines.append(f"🔹 **{k}**{alias_str}: {preview}")
        
        yield event.plain_result("\n".join(lines))

    @filter.command("导出预设")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def export_presets(self, event: AstrMessageEvent):
        try:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            export_path = os.path.join(str(self.data_dir), f"presets_export_{timestamp}.json")
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            await event.send_file(export_path)
        except Exception as e:
            yield event.plain_result(f"❌ 导出失败: {e}")

    @filter.command("导入预设")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def import_presets(self, event: AstrMessageEvent):
        yield event.plain_result("⚠️ 请使用 WebUI 配置或手动替换后台文件。")
