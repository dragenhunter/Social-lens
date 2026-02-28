"""Comment scraping helpers.

Provides an async `list_comments` function that extracts visible comments
from the current Playwright `page`. If `deep=True` it will attempt to
click any "View more comments" / "Load more comments" buttons a few
times to reveal additional comments.
"""

from typing import List, Dict, Any
from config.settings import DEEP_COMMENT_LOADING


async def list_comments(page, deep: bool = False, max_comments: int = 200) -> List[Dict[str, Any]]:
    """Extract a list of comments from the current post page/context.

    Parameters:
    - `page`: Playwright `Page` instance already focused on a post
    - `deep`: attempt to expand additional comments by clicking view-more buttons
    - `max_comments`: upper bound on comments to return

    Returns a list of dicts: {"author": str, "text": str}
    """
    try:
        # optionally try to expand more comments
        if deep or DEEP_COMMENT_LOADING:
            for _ in range(6):
                try:
                    # common Instagram label variants
                    btn = await page.query_selector('button:has-text("View all comments")')
                    if not btn:
                        btn = await page.query_selector('button:has-text("Load more comments")')
                    if not btn:
                        btn = await page.query_selector('text=View all comments')
                    if not btn:
                        break
                    await btn.click()
                    await page.wait_for_timeout(300)
                except Exception:
                    break

        # evaluate DOM for comment nodes
        comments = await page.evaluate("""
        () => {
            const out = [];
            // Comments are often inside nested ULs under the article/dialog
            const nodes = document.querySelectorAll('ul ul li');
            for (const n of nodes) {
                try {
                    const author = n.querySelector('a')?.innerText || n.querySelector('h3')?.innerText || '';
                    const span = n.querySelector('span');
                    const text = span ? span.innerText : n.innerText || '';
                    // ignore very short or empty nodes
                    if (text && text.trim().length>0) out.push({author: author.trim(), text: text.trim()});
                } catch(e) { /* continue */ }
            }
            return out;
        }
        """
        )

        if not isinstance(comments, list):
            return []

        # Apply max_comments limit
        return comments[:max_comments]
    except Exception:
        return []

