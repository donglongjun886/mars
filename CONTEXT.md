# Mars

Mars is a single-user Python CLI coding agent. This glossary fixes the vocabulary shared by the design docs and the code.

## Language

**Turn**:
一条用户输入到模型停止之间的全部过程。会话结束时打印的"轮数"即 turn 数。
_Avoid_: round, iteration

**Step**:
turn 内的一次模型请求及其触发的工具批次；一个 turn 含 1..n 个 step。
_Avoid_: round, loop iteration

**Event**:
主循环在运行时发出的对象，不持久化，只供渲染与测试消费。
_Avoid_: message

**Entry**:
写入会话日志的持久行；只有完成态节点会成为 entry。
_Avoid_: record, line

**Session**:
一次可恢复的完整对话历史，由若干 turn 组成。
_Avoid_: conversation, chat

**Delta**:
流式输出的一段增量，正文与推理各一种，只作为 event 存在。
_Avoid_: chunk, token

**Tool call**:
模型请求执行一次工具的动作，必须与一条 tool result 配对。
_Avoid_: invocation, function call

**Tool result**:
工具执行后的回灌结果；失败也表示为 result（`is_error`），而不是异常。
_Avoid_: error, output

**Spill**:
超长工具输出的完整文件副本；回灌给模型的是路径而非全文。
_Avoid_: overflow, dump
