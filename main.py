import asyncio
import os
import re

import yaml

from pkg.platform.types.message import MessageChain, Plain
from pkg.plugin.context import register, handler, BasePlugin, APIHost, EventContext
from pkg.plugin.events import NormalMessageResponded, PersonNormalMessageReceived, GroupNormalMessageReceived


# 注册插件
@register(name="SplitTypingPlugin", description="模拟人类打字习惯的消息分段发送插件", version="0.1", author="小馄饨")
class DelayedResponsePlugin(BasePlugin):
    # 默认配置
    default_config = {
        # 每个字符的延迟时间(秒)
        "delay_per_char": 0.5,
        # 允许分段功能
        "enable_split": True,
        # 删除推理过程
        "hide_reasoning_content": True,
        # 超过该字符数的消息将不会分段 (设为0表示不限制)
        "max_chars_for_split": 100,
        # 需要保留的标点符号
        "keep_punctuation": ["？", "！", "?", "!", "~", "〜"],
        # 需要删除的标点符号
        "skip_punctuation": ["，", "。", ",", ".", ":", "：", "\n"],
        # 作为分段标记的标点符号
        "split_punctuation": ["？", "！", "?", "!", "〜"]
    }

    # 插件加载时触发
    def __init__(self, host: APIHost):
        super().__init__(host)
        self.config = self.default_config.copy()
        self.config_file = os.path.join(os.path.dirname(__file__), "config.yaml")
        self.load_config()

    # 加载配置
    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                if config:
                    self.config = config
                    self.host.ap.logger.info(f"插件已加载配置：{self.config}")
            except Exception as e:
                self.host.ap.logger.error(f"插件加载配置失败：{e}")
        else:
            # 创建默认配置文件
            self.save_config()

    # 保存配置
    def save_config(self):
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                yaml.dump(self.config, f, allow_unicode=True)
            self.host.ap.logger.info("插件已保存配置")
        except Exception as e:
            self.host.ap.logger.error(f"插件保存配置失败：{e}")

    # 异步初始化
    async def initialize(self):
        self.host.ap.logger.info("插件已初始化")

    # 删除<think>标签内的推理过程
    def hide_reasoning_content(self, text_message: str) -> str:
        if not self.config.get('hide_reasoning_content', True):
            # 未开启隐藏功能, 返回原始内容
            return text_message
        # 开启隐藏功能, 返回正则处理后的内容
        return re.sub(r"<think>.*?</think>", "", text_message, flags=re.DOTALL).strip()

    # 智能分段文本
    def split_text(self, text: str) -> list:
        # 获取字符长度限制
        max_chars = self.config.get("max_chars_for_split", 100)

        # 如果文本长度超过限制，不进行分段
        if 0 < max_chars < len(text):
            self.host.ap.logger.debug(f"文本长度为 {len(text)} 字符，超过限制 {max_chars}，不进行分段")
            return [text]

        # 如果不启用分段，直接返回原文本
        if not self.config.get("enable_split", True):
            return [text]

        # 先处理括号内的内容
        segments = []
        current = ""
        in_parentheses = False

        # 需要删除的标点符号
        skip_punctuation = self.config.get("skip_punctuation", ["，", "。", ",", ".", ":", "：", "\n"])
        # 作为分段标记的标点符号
        split_punctuation = self.config.get("split_punctuation", ["？", "！", "?", "!"])

        for i, char in enumerate(text):
            if char == '(':
                in_parentheses = True
                if current.strip():
                    segments.append(current.strip())
                current = char
            elif char == ')':
                in_parentheses = False
                current += char
                segments.append(current.strip())
                current = ""
            elif char in skip_punctuation and not in_parentheses:
                continue
            else:
                current += char
                # 如果不在括号内且遇到分隔符，进行分段
                if not in_parentheses and char in split_punctuation:
                    segments.append(current.strip())
                    current = ""

        # 处理最后剩余的文本
        if current.strip():
            segments.append(current.strip())

        return [seg for seg in segments if seg.strip()]

    # 处理私聊消息命令
    @handler(PersonNormalMessageReceived)
    async def on_person_message_received(self, ctx: EventContext):
        await self.process_command(ctx)

    # 处理群聊消息命令
    @handler(GroupNormalMessageReceived)
    async def on_group_message_received(self, ctx: EventContext):
        await self.process_command(ctx)

    # 处理命令
    async def process_command(self, ctx: EventContext):
        # 获取消息文本
        message = ctx.event.text_message.strip()

        # 处理开启/关闭分段命令
        if message == "/开启分段":
            self.config["enable_split"] = True
            self.save_config()

            # 回复用户
            response = "已开启消息分段发送功能"
            ctx.add_return("reply", [response])
            ctx.prevent_default()

            self.host.ap.logger.info("已开启分段功能")

        elif message == "/关闭分段":
            self.config["enable_split"] = False
            self.save_config()

            # 回复用户
            response = "已关闭消息分段发送功能"
            ctx.add_return("reply", [response])
            ctx.prevent_default()

            self.host.ap.logger.info("已关闭分段功能")

        # 处理隐藏/显示推理过程命令
        elif message == "/显示推理":
            self.config["hide_reasoning_content"] = False
            self.save_config()

            # 回复用户
            response = "已关闭推理过程隐藏功能"
            ctx.add_return("reply", [response])
            ctx.prevent_default()

            self.host.ap.logger.info("已关闭推理过程隐藏功能")

        elif message == "/隐藏推理":
            self.config["hide_reasoning_content"] = True
            self.save_config()

            # 回复用户
            response = "已开启推理过程隐藏功能"
            ctx.add_return("reply", [response])
            ctx.prevent_default()

            self.host.ap.logger.info("已开启推理过程隐藏功能")

        # 设置字符数限制的命令
        elif message.startswith("/设置分段字符限制"):
            try:
                # 尝试提取数字
                limit = int(message.replace("/设置分段字符限制", "").strip())
                self.config["max_chars_for_split"] = limit
                self.save_config()

                # 回复用户
                if limit > 0:
                    response = f"已设置：超过 {limit} 个字符的消息将不会分段"
                else:
                    response = "已设置：不限制字符数，所有消息都可能分段"

                ctx.add_return("reply", [response])
                ctx.prevent_default()

                self.host.ap.logger.info(f"已设置分段字符限制为 {limit}")

            except ValueError:
                # 如果输入的不是数字
                response = "请输入正确的数字格式，例如：/设置分段字符限制 100"
                ctx.add_return("reply", [response])
                ctx.prevent_default()

    # 当AI回复消息时触发
    @handler(NormalMessageResponded)
    async def on_normal_message_responded(self, ctx: EventContext):
        # 获取回复消息
        response_text = self.hide_reasoning_content(ctx.event.response_text)

        # 如果没有回复消息，不处理
        if not response_text:
            return

        # 记录原始回复
        self.host.ap.logger.debug(f"DelayedResponse插件拦截到原始回复: {response_text}")

        # 智能分段
        segments = self.split_text(response_text)
        self.host.ap.logger.debug(f"DelayedResponse插件分段结果: {segments}")

        # 如果没有分段，或者只有一个分段，将输出设置为隐藏推理过程的结果
        if not segments or len(segments) == 1:
            ctx.add_return("reply", [response_text])
            return

        # 阻止默认行为
        ctx.prevent_default()

        # 创建发送消息的异步任务
        asyncio.create_task(self.send_messages(ctx, segments))

    # 异步发送多条消息
    async def send_messages(self, ctx: EventContext, segments):
        # 获取每个字符的延迟时间
        delay_per_char = self.config.get("delay_per_char", 0.5)

        # 按顺序发送每个分段
        for segment in segments:
            # 创建消息链
            message_chain = MessageChain([Plain(segment)])

            # 发送消息
            await ctx.reply(message_chain)

            # 根据分段长度计算延迟时间
            delay_time = len(segment) * delay_per_char
            await asyncio.sleep(delay_time)

    # 插件卸载时触发
    def __del__(self):
        pass
