"""业务服务层包。

services 可以理解为“业务逻辑集中区”。

新手理解：
- routes/ 负责 HTTP：接收请求、返回响应。
- schemas/ 负责数据格式：定义请求体和响应体长什么样。
- services/ 负责业务：真正决定“收到问题后应该怎么处理”。

当前阶段：
我们先创建 TutorAgentService 的空框架，
下一步你会把 /chat 里固定返回 TutorReply 的逻辑搬到 service 里。
"""

# 这里先不强制导出具体服务类。
# 新手阶段保持显式导入更容易读懂：
# from app.services.tutor_agent_service import TutorAgentService
