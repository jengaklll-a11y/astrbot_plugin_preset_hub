import json
import os
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api.event import filter
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot import logger

@register("astrbot_plugin_preset_hub", "Antigravity", "全局预设中心", "1.0.0")
class PresetHub(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        # 获取 AstrBot 标准数据目录
        self.data_dir = StarTools.get_data_dir("astrbot_plugin_preset_hub")
        self.preset_file = os.path.join(str(self.data_dir), "global_presets.json")
        self.presets = {}
        
        # 初始化加载
        self._load_presets()
        logger.info(f"[PresetHub] 已加载 {len(self.presets)} 个全局预设")

    def _load_presets(self):
        """从文件加载预设"""
        if not os.path.exists(self.preset_file):
            # 初始化默认数据
            default_data = {
                "手办": "Transform this image into a high-quality figurine style, plastic texture, studio lighting",
                "二次元": "anime style, flat color, cel shading, high quality",
                "赛博朋克": "cyberpunk style, neon lights, high tech, futuristic city",
                "素描": "sketch style, pencil drawing, monochrome, high contrast",
                "油画": "oil painting style, thick brushstrokes, artistic, texture"
            }
            self._save_presets_to_file(default_data)
        
        try:
            with open(self.preset_file, 'r', encoding='utf-8') as f:
                self.presets = json.load(f)
        except Exception as e:
            logger.error(f"[PresetHub] 加载预设文件失败: {e}")
            self.presets = {}

    def _save_presets_to_file(self, data):
        """保存预设到文件"""
        os.makedirs(os.path.dirname(self.preset_file), exist_ok=True)
        try:
            with open(self.preset_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.presets = data
            return True
        except Exception as e:
            logger.error(f"[PresetHub] 保存预设失败: {e}")
            return False

    @filter.command("添加预设")
    async def add_preset(self, event: AstrMessageEvent, key: str, value: str):
        """
        添加或更新全局预设
        用法: /添加预设 关键词 提示词内容
        """
        if not key or not value:
            yield event.plain_result("❌ 格式错误。用法: /添加预设 关键词 提示词内容")
            return

        self.presets[key] = value
        if self._save_presets_to_file(self.presets):
            yield event.plain_result(f"✅ 全局预设已保存: [{key}]")
        else:
            yield event.plain_result(f"❌ 保存失败，请查看后台日志")

    @filter.command("删除预设")
    async def del_preset(self, event: AstrMessageEvent, key: str):
        """
        删除全局预设
        用法: /删除预设 关键词
        """
        if key in self.presets:
            del self.presets[key]
            self._save_presets_to_file(self.presets)
            yield event.plain_result(f"🗑️ 已删除全局预设: [{key}]")
        else:
            yield event.plain_result(f"❌ 未找到预设: [{key}]")

    @filter.command("全局预设列表")
    async def list_presets(self, event: AstrMessageEvent):
        """列出所有可用的全局预设"""
        if not self.presets:
            yield event.plain_result("📭 当前没有全局预设，请使用 /添加预设 进行添加。")
            return

        msg = "🌏 全局预设列表 (所有绘图插件通用):\n" + "━" * 20 + "\n"
        for k, v in self.presets.items():
            # 截取过长的提示词，保持排版整洁
            display_v = v if len(v) < 30 else v[:28] + "..."
            msg += f"🔹 {k} : {display_v}\n"
        msg += "━" * 20
        yield event.plain_result(msg)

    @filter.command("查询预设")
    async def query_preset(self, event: AstrMessageEvent, key: str):
        """查看某个预设的完整内容"""
        if key in self.presets:
            yield event.plain_result(f"🔍 预设 [{key}] 的完整内容:\n\n{self.presets[key]}")
        else:
            yield event.plain_result(f"❌ 未找到预设: [{key}]")
