import json
import os
import shutil
from typing import Dict, Optional
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api.event import filter
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot import logger

@register("astrbot_plugin_preset_hub", "Antigravity", "全局预设中心", "1.1.0")
class PresetHub(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        # 获取 AstrBot 标准数据目录
        self.data_dir = StarTools.get_data_dir("astrbot_plugin_preset_hub")
        self.preset_file = os.path.join(str(self.data_dir), "global_presets.json")
        self.backup_file = os.path.join(str(self.data_dir), "global_presets.json.bak")
        
        # 数据结构回归简单: { "key": "prompt_content" }
        self.presets: Dict[str, str] = {}
        
        # 初始化加载
        self._load_presets()
        logger.info(f"[PresetHub] 已加载 {len(self.presets)} 个全局预设")

    # ================= 核心数据逻辑 =================

    def _load_presets(self):
        """从文件加载预设，包含向下兼容逻辑"""
        if not os.path.exists(self.preset_file):
            self._init_default_data()
            return
        
        try:
            with open(self.preset_file, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
            
            # 兼容性处理：如果之前的版本保存了 {"prompt": "...", "negative": "..."} 结构
            # 这里会自动将其“拍扁”回纯字符串，只保留 prompt 字段
            is_migrated = False
            for k, v in raw_data.items():
                if isinstance(v, dict) and "prompt" in v:
                    self.presets[k] = v["prompt"] # 只取正向词
                    is_migrated = True
                elif isinstance(v, str):
                    self.presets[k] = v
                else:
                    # 未知格式，强转字符串防报错
                    self.presets[k] = str(v)
            
            if is_migrated:
                logger.info("[PresetHub] 检测到复杂数据结构，已自动简化为纯文本格式")
                self._save_safe(self.presets)
                
        except Exception as e:
            logger.error(f"[PresetHub] 加载预设文件失败: {e}")
            self.presets = {}

    def _init_default_data(self):
        """初始化默认数据"""
        default_data = {
            "手办": "Transform this image into a high-quality figurine style, plastic texture, studio lighting",
            "二次元": "anime style, flat color, cel shading, high quality",
            "赛博朋克": "cyberpunk style, neon lights, high tech, futuristic city",
            "素描": "sketch style, pencil drawing, monochrome, high contrast",
            "油画": "oil painting style, thick brushstrokes, artistic, texture"
        }
        self.presets = default_data
        self._save_safe(default_data)

    def _save_safe(self, data: dict) -> bool:
        """安全保存：备份 -> 写入 -> 异常回滚"""
        os.makedirs(os.path.dirname(self.preset_file), exist_ok=True)
        try:
            # 1. 备份旧文件
            if os.path.exists(self.preset_file):
                shutil.copy(self.preset_file, self.backup_file)
            
            # 2. 写入数据
            with open(self.preset_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            self.presets = data
            return True
        except Exception as e:
            logger.error(f"[PresetHub] 保存预设失败: {e}")
            # 尝试恢复
            if os.path.exists(self.backup_file):
                shutil.copy(self.backup_file, self.preset_file)
            return False

    # ================= 公共接口 (供其他插件调用) =================

    def get_preset_prompt(self, key: str) -> Optional[str]:
        """直接返回提示词字符串"""
        return self.presets.get(key)

    def get_all_presets(self) -> Dict[str, str]:
        """获取所有预设"""
        return self.presets

    # ================= 指令交互 =================

    @filter.command("添加预设")
    @filter.permission_type(filter.PermissionType.ADMIN) # 仅管理员可用
    async def add_preset(self, event: AstrMessageEvent, key: str, value: str):
        """
        添加或更新全局预设
        用法: /添加预设 关键词 提示词内容
        """
        if not key or not value:
            yield event.plain_result("❌ 格式错误。用法: /添加预设 关键词 提示词内容")
            return

        self.presets[key] = value.strip()
        
        if self._save_safe(self.presets):
            yield event.plain_result(f"✅ 全局预设已保存: [{key}]\n内容: {value[:50]}{'...' if len(value)>50 else ''}")
        else:
            yield event.plain_result(f"❌ 保存失败，请查看后台日志")

    @filter.command("删除预设")
    @filter.permission_type(filter.PermissionType.ADMIN) # 仅管理员可用
    async def del_preset(self, event: AstrMessageEvent, key: str):
        """
        删除全局预设
        用法: /删除预设 关键词
        """
        if key in self.presets:
            del self.presets[key]
            self._save_safe(self.presets)
            yield event.plain_result(f"🗑️ 已删除全局预设: [{key}]")
        else:
            yield event.plain_result(f"❌ 未找到预设: [{key}]")

    @filter.command("全局预设列表")
    async def list_presets(self, event: AstrMessageEvent):
        """列出所有预设 Key"""
        if not self.presets:
            yield event.plain_result("📭 当前没有全局预设。")
            return

        keys = list(self.presets.keys())
        msg = f"🌏 全局预设列表 (共 {len(keys)} 个):\n" + "━" * 20 + "\n"
        # 简单排版：每行显示一个
        for k in keys:
            preview = self.presets[k][:20] + "..." if len(self.presets[k]) > 20 else self.presets[k]
            msg += f"🔹 {k}: {preview}\n"
        msg += "━" * 20 + "\n💡 使用 /查询预设 [关键词] 查看完整内容"
        yield event.plain_result(msg)

    @filter.command("查询预设")
    async def query_preset(self, event: AstrMessageEvent, key: str):
        """查看某个预设的完整内容"""
        content = self.presets.get(key)
        if content:
            yield event.plain_result(f"🔍 预设 [{key}] 的内容:\n\n{content}")
        else:
            yield event.plain_result(f"❌ 未找到预设: [{key}]")

    @filter.command("搜索预设")
    async def search_preset(self, event: AstrMessageEvent, keyword: str):
        """
        模糊搜索预设
        用法: /搜索预设 关键词
        """
        if not keyword:
            yield event.plain_result("❌ 请输入搜索关键词")
            return

        results = []
        for k, v in self.presets.items():
            # 搜索 Key 或者 Prompt 内容
            if keyword.lower() in k.lower() or keyword.lower() in v.lower():
                results.append(k)
        
        if results:
            yield event.plain_result(f"🔍 包含 '{keyword}' 的预设:\n" + " | ".join(results))
        else:
            yield event.plain_result(f"📭 未找到包含 '{keyword}' 的相关预设")
