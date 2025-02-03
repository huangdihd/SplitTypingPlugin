from pkg.plugin.context import register, handler, llm_func, BasePlugin, APIHost, EventContext
from pkg.plugin.events import *  # 导入事件类
from pkg.platform.types import Plain  # 导入消息类型
import re
import logging  # 添加 logging 模块
import asyncio
import yaml
import os
from collections import defaultdict

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 注册插件
@register(
    name="SplitTypingPlugin",  # 英文名
    description="模拟人类打字习惯的消息分段发送插件", # 中文描述
    version="0.1",
    author="小馄饨"
)
class MyPlugin(BasePlugin):

    # 插件加载时触发
    def __init__(self, host: APIHost):
        self.split_enabled = {}  # 用字典存储每个用户的分段状态
        self.typing_locks = defaultdict(asyncio.Lock)  # 每个对话的打字锁
        
        # 加载配置文件
        config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                settings = config.get('typing_settings', {})
                self.char_delay = settings.get('char_delay', 0.1)  # 每个字符的延迟
                self.segment_pause = settings.get('segment_pause', 0.5)  # 段落间停顿
                self.max_split_length = settings.get('max_split_length', 50)  # 最大分段长度
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            # 使用默认值
            self.char_delay = 0.1
            self.segment_pause = 0.5
            self.max_split_length = 50

    # 异步初始化
    async def initialize(self):
        pass

    def split_text(self, text: str) -> list:
        result = []
        temp = ''
        
        i = 0
        while i < len(text):
            char = text[i]
            
            # 如果遇到左括号，先保存之前的内容
            if char == '(':
                if temp.strip():
                    result.append(temp.strip())
                temp = ''
                # 收集括号内的内容（包括括号）
                bracket_content = char
                i += 1
                while i < len(text) and text[i] != ')':
                    bracket_content += text[i]
                    i += 1
                if i < len(text):  # 添加右括号
                    bracket_content += text[i]
                result.append(bracket_content)  # 括号作为独立的一段
                i += 1
                continue
            
            # 如果遇到数字序列
            if char.isdigit():
                if temp.strip():
                    result.append(temp.strip())
                temp = ''
                # 收集连续的数字
                number = char
                i += 1
                while i < len(text) and (text[i].isdigit() or text[i] in [',', '，']):
                    if text[i] not in [',', '，']:  # 跳过逗号
                        number += text[i]
                    i += 1
                result.append(number)
                continue
            
            # 处理感叹号
            if char in ['！', '!']:
                if temp.strip():
                    result.append(temp.strip() + char)
                temp = ''
                i += 1
                continue
            
            # 处理其他分隔符
            if char in ['，', '。', ',', '.']:
                if temp.strip():
                    result.append(temp.strip())
                temp = ''
                i += 1
                continue
            
            temp += char
            i += 1
        
        # 处理最后剩余的内容
        if temp.strip():
            result.append(temp.strip())
        
        return [part for part in result if part.strip()]

    # 当收到个人消息时触发
    @handler(PersonNormalMessageReceived)
    async def person_normal_message_received(self, ctx: EventContext):
        sender_id = ctx.event.sender_id
        msg = ctx.event.text_message

        # 处理开关命令
        if msg == "/开启分段":
            self.split_enabled[sender_id] = True
            logger.info(f"[分段发送] 用户 {sender_id} 开启了分段发送功能")
            await ctx.send_message("person", sender_id, [Plain("已开启分段发送模式")])
            ctx.prevent_default()
            return
        elif msg == "/关闭分段":
            self.split_enabled[sender_id] = False
            logger.info(f"[分段发送] 用户 {sender_id} 关闭了分段发送功能")
            await ctx.send_message("person", sender_id, [Plain("已关闭分段发送模式")])
            ctx.prevent_default()
            return

    # 当收到群消息时触发
    @handler(GroupNormalMessageReceived)
    async def group_normal_message_received(self, ctx: EventContext):
        group_id = ctx.event.group_id
        msg = ctx.event.text_message

        # 处理开关命令
        if msg == "/开启分段":
            self.split_enabled[group_id] = True
            logger.info(f"[分段发送] 群 {group_id} 开启了分段发送功能")
            await ctx.send_message("group", group_id, [Plain("已开启分段发送模式")])
            ctx.prevent_default()
            return
        elif msg == "/关闭分段":
            self.split_enabled[group_id] = False
            logger.info(f"[分段发送] 群 {group_id} 关闭了分段发送功能")
            await ctx.send_message("group", group_id, [Plain("已关闭分段发送模式")])
            ctx.prevent_default()
            return

    async def get_chat_lock(self, chat_type: str, chat_id: str) -> asyncio.Lock:
        """获取对话的锁"""
        lock_key = f"{chat_type}_{chat_id}"
        return self.typing_locks[lock_key]

    async def simulate_typing(self, ctx: EventContext, chat_type: str, chat_id: str, text: str):
        """模拟打字效果的延时"""
        # 获取此对话的锁
        lock = await self.get_chat_lock(chat_type, chat_id)
        
        # 等待获取锁
        async with lock:
            # 根据文本长度计算延时
            typing_delay = len(text) * self.char_delay
            # 发送完整消息
            await ctx.send_message(chat_type, chat_id, [Plain(text)])
            # 等待打字延时
            await asyncio.sleep(typing_delay)

    # 处理大模型的回复
    @handler(NormalMessageResponded)
    async def normal_message_responded(self, ctx: EventContext):
        chat_type = ctx.event.launcher_type
        chat_id = ctx.event.launcher_id if chat_type == "group" else ctx.event.sender_id
        
        # 检查是否启用分段
        if not self.split_enabled.get(chat_id, False):
            return

        # 获取大模型的回复文本
        response_text = ctx.event.response_text
        
        # 获取此对话的锁
        lock = await self.get_chat_lock(chat_type, chat_id)
        
        # 等待获取锁
        async with lock:
            # 如果文本长度超过最大分段长度，直接发送不分段
            if len(response_text) > self.max_split_length:
                logger.info(f"[分段发送] 文本长度({len(response_text)})超过最大限制({self.max_split_length})，将不进行分段")
                # 模拟整体打字延时并发送
                await self.simulate_typing(ctx, chat_type, chat_id, response_text)
                return
            
            # 分割文本
            parts = self.split_text(response_text)
            
            if parts:
                logger.info(f"[分段发送] {chat_type} {chat_id} 的消息将被分为 {len(parts)} 段发送")
                
                # 阻止默认的回复行为
                ctx.prevent_default()
                
                # 逐段发送消息
                for i, part in enumerate(parts, 1):
                    logger.info(f"[分段发送] 正在发送第 {i}/{len(parts)} 段: {part}")
                    # 模拟打字延时并发送
                    typing_delay = len(part) * self.char_delay
                    await ctx.send_message(chat_type, chat_id, [Plain(part)])
                    await asyncio.sleep(typing_delay)
                    
                    # 如果不是最后一段，添加段落间停顿
                    if i < len(parts):
                        await asyncio.sleep(self.segment_pause)

    # 插件卸载时触发
    def __del__(self):
        pass
