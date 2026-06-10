"""深度分析路由"""
import asyncio
import json
import logging
from datetime import datetime, timezone

import mistune
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse

from app.database import SessionLocal

_md = mistune.create_markdown()
from app.models.search import SearchRecord, SearchResultItem, AnalysisReport
from app.services.deepseek import call_deepseek, call_deepseek_stream
from app.utils.helpers import templates, template_context, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/report', tags=['分析'])

# ── 5 个独立章节的 Prompt（各自小 token，可并行生成）──
SECTION_PROMPTS = [
    {
        'id': 'summary',
        'title': '一、执行摘要',
        'icon': '📋',
        'prompt': """你是资深新闻分析师。基于以下{count}条关于"{keyword}"的新闻，撰写精炼的执行摘要。

{articles_text}

要求：200字以内，概括核心发现和要点。直接输出正文，不要标题前缀。""",
        'max_tokens': 512,
    },
    {
        'id': 'theme',
        'title': '二、交叉主题分析',
        'icon': '🔍',
        'prompt': """你是资深新闻分析师。基于以下{count}条关于"{keyword}"的新闻，进行交叉主题分析。

{articles_text}

要求：分析共同主题、叙事模式和关键差异，300字以内。直接输出正文，不要标题前缀。""",
        'max_tokens': 768,
    },
    {
        'id': 'credibility',
        'title': '三、来源可信度评估',
        'icon': '🛡️',
        'prompt': """你是资深新闻分析师。基于以下{count}条关于"{keyword}"的新闻，评估各来源可信度。

{articles_text}

要求：对每条新闻的来源进行权威性、立场和历史可信度评价，300字以内。直接输出正文，不要标题前缀。""",
        'max_tokens': 768,
    },
    {
        'id': 'perspective',
        'title': '四、多视角对比',
        'icon': '👁️',
        'prompt': """你是资深新闻分析师。基于以下{count}条关于"{keyword}"的新闻，进行多视角对比分析。

{articles_text}

要求：对比各新闻在报道角度、侧重点和立场上的异同，300字以内。直接输出正文，不要标题前缀。""",
        'max_tokens': 768,
    },
    {
        'id': 'evaluation',
        'title': '五、综合评估',
        'icon': '📊',
        'prompt': """你是资深新闻分析师。基于以下{count}条关于"{keyword}"的新闻，给出综合评估。

{articles_text}

要求：评价该主题的新闻价值、社会影响和发展趋势，300字以内。直接输出正文，不要标题前缀。""",
        'max_tokens': 768,
    },
]


@router.get('/{report_id}', response_class=HTMLResponse)
async def view_report(request: Request, report_id: int):
    """查看分析报告"""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url='/auth/login', status_code=302)

    db = SessionLocal()
    try:
        report = db.query(AnalysisReport).filter_by(
            id=report_id, user_id=user.id
        ).first()
        if not report:
            return HTMLResponse('<p style="color:red">报告不存在</p>', status_code=404)

        search = db.query(SearchRecord).get(report.search_id)
        ctx = template_context(request)
        ctx['report'] = report
        ctx['keyword'] = search.keyword if search else ''
        ctx['report_content'] = _md(report.report_content)  # Markdown → HTML
        ctx['generated_at'] = report.generated_at.strftime('%Y-%m-%d %H:%M')

        return templates.TemplateResponse('report.html', ctx)
    finally:
        db.close()


def _build_analysis_context(db, search_id: int, ids: list[int], user_id: int):
    """构建分析上下文：验证权限、获取文章、返回文章数据"""
    record = db.query(SearchRecord).filter_by(
        id=search_id, user_id=user_id
    ).first()
    if not record:
        return None, None, None

    articles = db.query(SearchResultItem).filter(
        SearchResultItem.id.in_(ids),
        SearchResultItem.search_id == search_id,
    ).all()

    if not articles:
        return None, record, None

    articles_text = '\n\n'.join([
        f'【新闻{i+1}】\n标题：{a.title}\n来源：{a.source_name}\n日期：{a.published_at}\n概要：{a.summary}'
        for i, a in enumerate(articles)
    ])

    return record, articles, articles_text


@router.post('/api/analyze')
async def execute_analysis(
    request: Request,
    search_id: int = Form(0),
    selected_ids: str = Form(''),
):
    """执行深度分析（非流式快速版）"""
    user = get_current_user(request)
    if not user:
        return JSONResponse({'error': '请先登录'}, status_code=401)

    if not search_id:
        return JSONResponse({'error': '缺少搜索ID'}, status_code=400)

    try:
        ids = [int(x.strip()) for x in selected_ids.split(',') if x.strip()]
    except ValueError:
        return JSONResponse({'error': '无效的文章ID'}, status_code=400)

    if not ids:
        return JSONResponse({'error': '请至少选择一条新闻进行分析'}, status_code=400)

    db = SessionLocal()
    try:
        record, articles, articles_text = _build_analysis_context(db, search_id, ids, user.id)
        if record is None:
            return JSONResponse({'error': '搜索记录不存在'}, status_code=404)
        if not articles:
            return JSONResponse({'error': '未找到选中的新闻'}, status_code=400)

        # 并行生成所有章节
        async def gen_section(section):
            prompt = section['prompt'].format(
                count=len(articles),
                keyword=record.keyword,
                articles_text=articles_text,
            )
            messages = [{'role': 'user', 'content': prompt}]
            text = await call_deepseek(messages, temperature=0.7, max_tokens=section['max_tokens'])
            return {
                'id': section['id'],
                'title': section['title'],
                'icon': section['icon'],
                'content': text.strip(),
            }

        tasks = [gen_section(s) for s in SECTION_PROMPTS]
        sections = await asyncio.gather(*tasks)

        # 组装完整报告
        full_text = '\n\n'.join([
            f"## {s['icon']} {s['title']}\n\n{s['content']}"
            for s in sections
        ])
        full_text = f"# 🔬 深度分析报告：{record.keyword}\n\n" + full_text

        report = AnalysisReport(
            search_id=search_id,
            user_id=user.id,
            analyzed_items=json.dumps(ids),
            report_content=full_text,
        )
        db.add(report)
        db.commit()
        db.refresh(report)

        return JSONResponse({
            'success': True,
            'report_id': report.id,
        })

    except Exception as e:
        logger.exception(f'Analysis error: {e}')
        return JSONResponse({'error': f'分析失败：{str(e)}'}, status_code=500)
    finally:
        db.close()


@router.post('/api/analyze/stream')
async def execute_analysis_stream(
    request: Request,
    search_id: int = Form(0),
    selected_ids: str = Form(''),
):
    """SSE 流式深度分析 — 5 章节并行生成，逐一推送（ChatGPT 风格渐进展示）"""
    user = get_current_user(request)
    if not user:
        return JSONResponse({'error': '请先登录'}, status_code=401)

    if not search_id:
        return JSONResponse({'error': '缺少搜索ID'}, status_code=400)

    try:
        ids = [int(x.strip()) for x in selected_ids.split(',') if x.strip()]
    except ValueError:
        return JSONResponse({'error': '无效的文章ID'}, status_code=400)

    if not ids:
        return JSONResponse({'error': '请至少选择一条新闻进行分析'}, status_code=400)

    db = SessionLocal()
    record, articles, articles_text = _build_analysis_context(db, search_id, ids, user.id)
    if record is None:
        db.close()
        return JSONResponse({'error': '搜索记录不存在'}, status_code=404)
    if not articles:
        db.close()
        return JSONResponse({'error': '未找到选中的新闻'}, status_code=400)
    keyword = record.keyword
    article_count = len(articles)
    db.close()

    async def event_stream():
        all_content = ''
        completed_sections = []

        async def gen_section(section):
            """生成单个章节"""
            prompt = section['prompt'].format(
                count=article_count,
                keyword=keyword,
                articles_text=articles_text,
            )
            messages = [{'role': 'user', 'content': prompt}]
            text = await call_deepseek(messages, temperature=0.7, max_tokens=section['max_tokens'])
            return {
                'id': section['id'],
                'title': section['title'],
                'icon': section['icon'],
                'content': text.strip(),
            }

        try:
            # 先发送章节清单，让前端占位
            yield f'data: {json.dumps({"type": "plan", "sections": [{"id": s["id"], "title": s["title"], "icon": s["icon"]} for s in SECTION_PROMPTS]})}\n\n'

            # 用 as_completed 并行生成，按完成顺序逐一推送
            tasks = [gen_section(s) for s in SECTION_PROMPTS]
            for coro in asyncio.as_completed(tasks):
                section = await coro
                completed_sections.append(section)

                # 逐个推送完成的章节（前端按完成顺序展示）
                yield f'data: {json.dumps({"type": "section", "id": section["id"], "title": section["title"], "icon": section["icon"], "content": section["content"], "done_count": len(completed_sections), "total": len(SECTION_PROMPTS)})}\n\n'

            # 按原始顺序组装完整报告保存
            completed_map = {s['id']: s for s in completed_sections}
            full_text = f"# 🔬 深度分析报告：{keyword}\n"
            for sec_def in SECTION_PROMPTS:
                sec = completed_map.get(sec_def['id'])
                if sec:
                    full_text += f"\n## {sec['icon']} {sec['title']}\n\n{sec['content']}\n"

            db2 = SessionLocal()
            report_id = None
            try:
                report = AnalysisReport(
                    search_id=search_id,
                    user_id=user.id,
                    analyzed_items=json.dumps(ids),
                    report_content=full_text,
                )
                db2.add(report)
                db2.commit()
                db2.refresh(report)
                report_id = report.id
            finally:
                db2.close()

            yield f'data: {json.dumps({"type": "done", "report_id": report_id})}\n\n'

        except Exception as e:
            logger.exception(f'Stream analysis error: {e}')
            yield f'data: {json.dumps({"type": "error", "message": str(e)})}\n\n'

    return StreamingResponse(
        event_stream(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    )
