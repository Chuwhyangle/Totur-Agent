"""具体接口路由包。

这个目录里的每个文件，通常负责一组接口。

例如：
- chat.py 负责聊天相关接口。
- health.py 负责健康检查接口。

每个路由文件一般会创建自己的 router = APIRouter(...)，
然后在 app/main.py 里用 app.include_router(...) 注册进去。
"""
