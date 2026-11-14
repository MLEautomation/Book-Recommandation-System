import { request, escapeHtml } from "./api.js";

export async function loadMyComments(page = 1) {
  const data = await request(`/me/comments?page=${page}`);
  const target = document.querySelector("#myComments");
  target.innerHTML =
    data.items
      .map(
        (item) => `<article class="comment-record">
    <a class="comment-book" href="/book/${item.book.id}#comment-${item.id}">
      <div class="comment-book-cover">${item.book.cover_path ? `<img src="${escapeHtml(item.book.cover_path)}" alt="">` : escapeHtml(item.book.title.slice(0, 1))}</div>
      <div><strong>${escapeHtml(item.book.title)}</strong><div class="muted">${escapeHtml(item.book.author)}</div></div>
    </a>
    <div class="comment-record-body"><div class="comment-content">${escapeHtml(item.content)}</div><div class="muted">${item.created_at} · 赞 ${item.likes} · 踩 ${item.dislikes}</div><button class="btn btn-danger btn-xs" data-delete-comment="${item.id}">撤回评论</button></div>
  </article>`,
      )
      .join("") || '<div class="empty">暂时没有评论</div>';
  target.querySelectorAll("[data-delete-comment]").forEach((button) => {
    button.onclick = async () => {
      if (!window.confirm("撤回后评论及其回复会被删除，确定继续吗？")) return;
      await request(`/comments/${button.dataset.deleteComment}`, {
        method: "DELETE",
      });
      await loadMyComments(page);
    };
  });
  const pager = document.querySelector("#myCommentsPager");
  pager.innerHTML =
    data.pages > 1
      ? `<div class="pager"><button class="btn btn-outline" data-page="${page - 1}" ${page <= 1 ? "disabled" : ""}>上一页</button><span class="muted">第 ${page} / ${data.pages} 页</span><button class="btn btn-outline" data-page="${page + 1}" ${page >= data.pages ? "disabled" : ""}>下一页</button></div>`
      : "";
  pager
    .querySelectorAll("[data-page]")
    .forEach(
      (button) =>
        (button.onclick = () => loadMyComments(Number(button.dataset.page))),
    );
}
