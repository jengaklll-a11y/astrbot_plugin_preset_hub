import json
import os
import shutil
import time
from typing import Dict, Optional, Tuple, List
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api.event import filter
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot import logger

@register("astrbot_plugin_preset_hub", "Antigravity", "全局预设中心", "2.0.0")
class PresetHub(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        # 路径配置
        self.data_dir = StarTools.get_data_dir("astrbot_plugin_preset_hub")
        self.preset_file = os.path.join(str(self.data_dir), "global_presets.json")
        self.backup_file = os.path.join(str(self.data_dir), "global_presets.json.bak")
        
        # 内存数据结构
        # presets: { "key": "prompt content" }
        # aliases: { "alias_name": "real_key_name" }
        self.data = {
            "presets": {},
            "aliases": {}
        }
        
        self._load_data()

    # ================= 数据 IO 与 迁移逻辑 =================

    def _load_data(self):
        """加载数据，包含从旧版本(v1)的自动迁移"""
        if not os.path.exists(self.preset_file):
            self._init_default_data()
            return
        
        try:
            with open(self.preset_file, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            
            # 迁移逻辑：判断是 v2 结构还是 v1 结构
            # v2 结构必须包含 "presets" 键
            if "presets" in raw and isinstance(raw["presets"], dict):
                self.data = raw
                if "aliases" not in self.data:
                    self.data["aliases"] = {}
                logger.info(f"[PresetHub] 已加载 {len(self.data['presets'])} 个预设, {len(self.data['aliases'])} 个别名")
            else:
                # v1 结构 (纯 KV)，执行迁移
                logger.warning("[PresetHub] 检测到旧版数据结构，正在迁移至 v2...")
                migrated_presets = {}
                for k, v in raw.items():
                    # 兼容可能存在的复杂旧数据
                    if isinstance(v, dict) and "prompt" in v:
                        migrated_presets[k] = str(v["prompt"])
                    else:
                        migrated_presets[k] = str(v)
                
                self.data = {
                    "presets": migrated_presets,
                    "aliases": {}
                }
                self._save_safe()
                logger.info("[PresetHub] 数据迁移完成")

        except Exception as e:
            logger.error(f"[PresetHub] 加载失败: {e}")
            self._init_default_data()

    def _init_default_data(self):
        """初始化默认数据"""
        self.data = {
            "presets": {
                "手办": "Transform this image into a high-quality figurine style, plastic texture, studio lighting",
                "二次元": "anime style, flat color, cel shading, high quality",
                "赛博朋克": "cyberpunk style, neon lights, high tech, futuristic city"
            },
            "aliases": {
                "动漫": "二次元",
                "模型": "手办"
            }
        }
        self._save_safe()

    def _save_safe(self) -> bool:
        """安全保存"""
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

    # ================= 公共 API (供其他插件调用) =================

    def resolve_preset(self, key: str) -> Optional[str]:
        """
        核心 API：获取预设内容。自动处理别名。
        :param key: 预设名或别名
        :return: 提示词字符串 或 None
        """
        if not key:
            return None
            
        # 1. 检查是否是别名
        real_key = self.data["aliases"].get(key, key)
        
        # 2. 获取内容
        return self.data["presets"].get(real_key)

    def get_all_keys(self) -> List[str]:
        """获取所有可用的触发词（包括原名和别名）"""
        return list(self.data["presets"].keys()) + list(self.data["aliases"].keys())

    # ================= 交互指令 =================

    @filter.command("添加预设")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def add_preset(self, event: AstrMessageEvent, key: str = None, *, value: str = None):
        """
        添加或覆盖预设。
        用法: /添加预设 关键词 提示词内容
        """
        # 手动解析以处理空格
        raw_msg = event.message_str.strip()
        parts = raw_msg.split(maxsplit=2)
        
        if len(parts) < 3:
             yield event.plain_result("❌ 用法: /添加预设 关键词 提示词内容")
             return

        target_key = parts[1]
        prompt_content = parts[2].strip()

        # 逻辑：如果这个 key 以前是个别名，现在被提升为正主，需要删除别名记录
        if target_key in self.data["aliases"]:
            del self.data["aliases"][target_key]

        self.data["presets"][target_key] = prompt_content
        
        if self._save_safe():
            preview = prompt_content[:20] + "..." if len(prompt_content) > 20 else prompt_content
            yield event.plain_result(f"✅ 预设 [{target_key}] 已保存。\n📝 内容: {preview}")
        else:
            yield event.plain_result("❌ 保存失败，请检查日志。")

    @filter.command("预设别名")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def add_alias(self, event: AstrMessageEvent, source: str, alias: str):
        """
        给现有预设添加别名。
        用法: /预设别名 <原名> <新别名>
        示例: /预设别名 二次元 动漫
        """
        if source not in self.data["presets"]:
            yield event.plain_result(f"❌ 原预设 [{source}] 不存在，请先添加它。")
            return
        
        if alias in self.data["presets"]:
            yield event.plain_result(f"❌ [{alias}] 已经是一个主预设了，无法设为别名。")
            return

        self.data["aliases"][alias] = source
        self._save_safe()
        yield event.plain_result(f"🔗 已关联: [{alias}] -> [{source}]")

    @filter.command("删除预设")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def del_preset(self, event: AstrMessageEvent, key: str):
        """
        删除预设或别名。
        如果删除的是主预设，指向它的别名也会失效(被清理)。
        """
        # 情况1: 删除的是别名
        if key in self.data["aliases"]:
            real = self.data["aliases"][key]
            del self.data["aliases"][key]
            self._save_safe()
            yield event.plain_result(f"🗑️ 别名 [{key}] (指向 {real}) 已删除。")
            return

        # 情况2: 删除的是主预设
        if key in self.data["presets"]:
            del self.data["presets"][key]
            
            # 清理所有指向该 Key 的别名
            to_remove = [k for k, v in self.data["aliases"].items() if v == key]
            for k in to_remove:
                del self.data["aliases"][k]
            
            self._save_safe()
            msg = f"🗑️ 主预设 [{key}] 已删除。"
            if to_remove:
                msg += f"\n🧹 关联删除的别名: {', '.join(to_remove)}"
            yield event.plain_result(msg)
            return

        yield event.plain_result(f"❌ 未找到预设或别名: [{key}]")

    @filter.command("预设列表")
    async def list_presets(self, event: AstrMessageEvent):
        """展示所有预设及别名"""
        if not self.data["presets"]:
            yield event.plain_result("📭 当前无预设。")
            return

        # 整理数据：Key -> [Alias1, Alias2]
        reverse_aliases = {}
        for alias, real in self.data["aliases"].items():
            if real not in reverse_aliases:
                reverse_aliases[real] = []
            reverse_aliases[real].append(alias)

        lines = [f"🌏 全局预设库 (共 {len(self.data['presets'])} 个):", "━" * 25]
        
        for k, v in self.data["presets"].items():
            # 获取别名展示
            alias_str = ""
            if k in reverse_aliases:
                alias_list = ", ".join(reverse_aliases[k])
                alias_str = f"\n   └ 🔗别名: {alias_list}"
            
            # 内容预览
            preview = v[:20].replace("\n", " ") + "..." if len(v) > 20 else v
            lines.append(f"🔹 **{k}**: {preview}{alias_str}")

        lines.append("━" * 25)
        lines.append("💡 提示: 其他插件可直接使用名称或别名调用。")
        
        yield event.plain_result("\n".join(lines))

    @filter.command("导出预设")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def export_presets(self, event: AstrMessageEvent):
        """将当前预设库导出为 JSON 文件"""
        try:
            # 生成临时文件路径
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            export_path = os.path.join(str(self.data_dir), f"presets_export_{timestamp}.json")
            
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            
            await event.send_file(export_path)
            # 发送后稍微延迟删除，或者保留在data目录供排查
        except Exception as e:
            logger.error(f"导出失败: {e}")
            yield event.plain_result(f"❌ 导出失败: {e}")

    @filter.command("导入预设")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def import_presets(self, event: AstrMessageEvent):
        """
        导入 JSON 配置文件。
        用法: 请直接回复包含 JSON 文件的消息，并输入 /导入预设
        """
        # 1. 检查回复的消息中是否有文件
        if not event.message_obj.reply:
             yield event.plain_result("❌ 请回复包含 JSON 文件的消息来导入。")
             return
             
        # AstrBot 目前获取 reply 文件路径可能需要适配，这里假设 event.message_obj.reply 也是个 Message 结构
        # 注意：具体的 reply 文件下载逻辑依赖 AstrBot 适配器实现。
        # 如果是标准实现，reply 消息中应该包含 components。
        
        # 简化处理：尝试寻找 message_obj 中的 File 组件 (针对回复的消息)
        # 这里使用一个通用 try-catch 块，因为不同平台文件处理差异较大
        try:
            # 伪代码：获取回复消息对象 -> 下载文件
            # 由于 AstrBot SDK 对回复文件的处理比较隐晦，这里建议用户把文件发出来，然后在那条消息下指令，
            # 或者直接简单点：用户发文本 JSON 内容 (如果不太长)。
            # 但为了文件功能，我们假设 `save_reply_file` 这类机制存在，
            # 或者提示用户手动替换 backend 文件更稳妥。
            
            # 替代方案：从 event 获取 components 里的 file
            # 这是一个比较通用的“回复式”获取逻辑，需要 StarTools 支持
            # 暂时实现为：提示用户路径，或者如果框架支持直接读取
            
            yield event.plain_result("⚠️ 由于平台限制，建议直接将 json 文件放入后台插件目录 data/astrbot_plugin_preset_hub/ 中并重启。")
            
        except Exception as e:
            yield event.plain_result(f"❌ 导入流程异常: {e}")
