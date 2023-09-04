# ----- coding: utf-8 ------
# author: YAO XU time:
import os
import pickle
from typing import Union
from sqlalchemy import event
from fastapi import Request, Depends, Body
from sqlalchemy.orm import sessionmaker
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import APIRouter, UploadFile
from sqlalchemy import select, text, func
from starlette.background import BackgroundTasks
import datetime
from fastapi import HTTPException
from app.Fast_blog.apps.AdminApp.superuserAdmin import oauth2_scheme
from app.Fast_blog.database.database import engine, db_session
from app.Fast_blog.middleware.backlist import BlogCache
from app.Fast_blog.model.models import Blog, BlogRating
import shutil
from collections import defaultdict

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
session = SessionLocal()

BlogApp = APIRouter()

templates = Jinja2Templates(directory="./Fast_blog/templates")

static_folder_path = os.path.join(os.getcwd(), "Fast_blog", "static")
BlogApp.mount("/static", StaticFiles(directory=static_folder_path), name="static")


@BlogApp.post('/blogadd')
async def BlogAdd(Addtitle: str, Addcontent: str, Addauthor: str, file: UploadFile, background_tasks: BackgroundTasks,
                  request: Request, ):
    async with db_session() as session:
        try:
            # 将文件保存到磁盘
            file_path = os.path.join(static_folder_path, "uploadimages", file.filename)
            with open(file_path, "wb") as f:
                shutil.copyfileobj(file.file, f)

            base_url = str(request.base_url)
            # 构建完整的URL地址
            image_url = f"{base_url.rstrip('/')}/static/uploadimages/{file.filename}"
            # 构建参数值字典
            params = {
                "title": Addtitle,
                "content": Addcontent,
                "BlogIntroductionPicture": image_url,  # 使用完整的URL地址
                "author": Addauthor,
                "created_at": datetime.datetime.now()
            }
            # 执行插入操作
            insert_statement = text(
                "INSERT INTO blogtable (title, content, `BlogIntroductionPicture`, author, created_at) "
                "VALUES (:title, :content, :BlogIntroductionPicture, :author, :created_at)").params(**params)
            await session.execute(insert_statement)
            await session.commit()

            return {'message': '文章已经添加到对应数据库', 'image_url': image_url}

        except Exception as e:
            print("我们遇到了下面的问题", {"data": e})


##序列化输出示例代码
# @BlogApp.get("/BlogIndex")
# ##博客首页API
# async def BlogIndex():
#     async with db_session() as session:
#         try:
#             stmt = select(models.Blog).order_by(models.Blog.BlogId)
#             result = await session.execute(text("select * from blogtable LIMIT 3;"))
#             results = result.fetchall()
#             results = [tuple(row) for row in results]
#             print(f"{type(results)} of type {type(results[0])}")
#             # <class 'list'> of type <class 'tuple'>
#             json_string = json.dumps(results,ensure_ascii=False)
#             return ({"data":json_string})
#         except Exception as e:
#             print("我们遇到了下面的问题")
#             print(e)
#         return 0

@BlogApp.get("/blog/BlogIndex")
async def BlogIndex(initialLoad: bool = True, page: int = 1, pageSize: int = 4):
    async with db_session() as session:
        try:
            offset = (page - 1) * pageSize
            columns = [Blog.BlogId, Blog.title, Blog.created_at, Blog.author, Blog.BlogIntroductionPicture]
            stmt = select(*columns).offset(offset).limit(pageSize)
            results = await session.execute(stmt)
            data = results.fetchall()
            data_dicts = []
            for row in data:
                data_dict = {
                    "BlogId": row[0],
                    "title": row[1],
                    "created_at": row[2],
                    "author": row[3],
                    "BlogIntroductionPicture": row[4],
                }
                data_dicts.append(data_dict)
            print(data_dicts)
            return data_dicts
        except Exception as e:
            print("我们遇到了下面的问题")
            print(e)
        return []

@BlogApp.get("/blog/AdminBlogIndex")
##博客首页API
async def AdminBlogIndex(token: str = Depends(oauth2_scheme)):
    async with db_session() as session:
        try:
            results = await session.execute(select(Blog))
            data = results.scalars().all()
            data = [item.to_dict() for item in data]
            print(data)
            return {"code": 20000,"data":data}
        except Exception as e:
            print("我们遇到了下面的问题")
            print(e)
        return 0


blog_cache = BlogCache()


# Create event listener to update cache
@event.listens_for(Blog, 'after_insert')
@event.listens_for(Blog, 'after_update')
@event.listens_for(Blog, 'after_delete')
def update_cache(mapper, connection, target):
    redis_key = f"blog_{target.BlogId}"
    data = {
        "BlogId": target.BlogId,
        "title": target.title,
        "content": target.content,
        "author": target.author,
        "BlogIntroductionPicture": target.BlogIntroductionPicture,
        "created_at": target.created_at,
    }
    blog_cache.redis_client.set(redis_key, pickle.dumps([data]))
    blog_cache.redis_client.expire(redis_key, 3600)  # Set expiration time to 1 hour


@BlogApp.post("/user/Blogid")
async def Blogid(blog_id: int):
    async with db_session() as session:
        redis_key = f"blog_{blog_id}"
        cached_data = blog_cache.redis_client.get(redis_key)
        if cached_data:
            print('从缓存中读取')
            cached_data_obj = pickle.loads(cached_data)
            return cached_data_obj
        else:
            print('从数据库中读取')
            results = await session.execute(select(Blog).filter(Blog.BlogId == blog_id))
            data = results.scalars().all()
            data = [item.to_dict() for item in data]
            blog_cache.redis_client.set(redis_key, pickle.dumps(data))
            blog_cache.redis_client.expire(redis_key, 3600)
            return data


@BlogApp.post("/blog/Blogid")
##博客详情页API
async def AdminBlogid(blog_id: int,token: str = Depends(oauth2_scheme)):
    async with db_session() as session:
        try:
            results = await session.execute(select(Blog).filter(Blog.BlogId == blog_id))
            data = results.scalars().all()
            data = [item.to_dict() for item in data]
            return {"code":20000,"data":data}
        except Exception as e:
            print("我们遇到了下面的问题")
            print(e)
        return []

@BlogApp.post("/blog/Blogedit")
##博客详情页API
async def AdminBlogidedit(blog_id: int, request_data: dict = Body(...), token: str = Depends(oauth2_scheme)):
    async with db_session() as session:
        try:

            # 根据 BlogId 查询相应的博客
            blog = await session.execute(select(Blog).where(Blog.BlogId == blog_id))
            blog_entry = blog.scalar_one()
            # 更新博客内容
            for key, value in request_data.items():
                if key == 'content':
                    # 编码字符串为二进制
                    setattr(blog_entry, key, bytes(value, encoding='utf-8'))
                else:
                    setattr(blog_entry, key, value)
            # 提交事务
            await session.commit()
            return {"code": 20000, "message": "更新成功"}
        except Exception as e:
            print("遇到了问题")
            print(e)
            await session.rollback()  # 发生错误时回滚事务
            return {"code": 50000, "message": "更新失败"}


# 创建一个字典来跟踪设备的投票次数
device_votes = defaultdict(int)


@BlogApp.post("/blogs/{blog_id}/ratings/")
async def rate_blog(blog_id: str, rating: int, device_id: str):  # 添加设备标识符参数
    if not (1 <= rating <= 5):
        raise HTTPException(status_code=400, detail="评分必须在1到5之间")
    # 检查设备是否已经投过票
    if device_votes[device_id] >= 1:
         raise HTTPException(status_code=400, detail="每台设备只能投一次票")
    async with db_session() as session:
        blog = await session.execute(select(Blog).where(Blog.BlogId == blog_id))
        if blog.scalar() is None:
            raise HTTPException(status_code=404, detail="博客文章不存在")
        # 在这里将rating转换为整数
        rating = int(rating)
        await session.execute(
            BlogRating.__table__.insert().values(
                blog_id=blog_id, rating=rating
            )
        )
        # 增加设备投票次数
        device_votes[device_id] += 1
        await session.commit()
        return {"message": "评分成功"}


@BlogApp.get("/blogs/{blog_id}/average-rating/", response_model=Union[float, int])
async def get_average_rating(blog_id: int):
    async with db_session() as session:
        blog = await session.execute(select(Blog).where(Blog.BlogId == blog_id))
        if blog.scalar() is None:
            return 0  # 返回默认值 0，表示从未评分过
        average_rating = await session.execute(
            select(func.avg(BlogRating.rating)).filter(BlogRating.blog_id == blog_id)
        )
        average_rating = average_rating.scalar()
        if average_rating is not None:
            return int(round(average_rating))
        else:
            return 0  # 返回默认值 0，表示从未评分过