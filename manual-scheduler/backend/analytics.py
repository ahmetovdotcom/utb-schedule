"""Authenticated reporting proxy; the UTB2 secret never reaches the browser."""
import httpx
from fastapi import APIRouter, HTTPException, Query, Response
from publication import destination

router = APIRouter(prefix='/api/analytics', tags=['Analytics'])


@router.get('')
async def summary(response: Response, days: int = Query(30, ge=1, le=180)):
    response.headers['Cache-Control'] = 'no-store'
    url, key = destination()
    url = url.rsplit('/', 1)[0] + '/analytics/summary'
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            result = await client.get(url, params={'days': days}, headers={'Authorization': f'Bearer {key}'})
            result.raise_for_status()
            data = result.json()
            if not isinstance(data, dict) or not isinstance(data.get('totals'), dict) or not isinstance(data.get('daily'), list):
                raise ValueError('Invalid analytics response')
    except (httpx.HTTPError, ValueError) as error:
        raise HTTPException(502, 'Не удалось получить статистику UTB2. Проверьте подключение и ключ публикации.') from error
    return data
