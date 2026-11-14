import { request, escapeHtml } from "./api.js";

async function loadFavorites(page = 1) {
  const data = await request(`/me/favorites?page=${page}`);
  const target = document.querySelector("#favoriteBooks");
  target.innerHTML =
    data.items
      .map(
        (book) => `<article class="favorite-record">
    <a href="/book/${book.id}">${book.cover_path ? `<img src="${escapeHtml(book.cover_path)}" alt="${escapeHtml(book.title)}封面">` : `<div class="comment-book-cover">${escapeHtml(book.title.slice(0, 1))}</div>`}</a>
    <div class="favorite-info"><a href="/book/${book.id}"><strong>${escapeHtml(book.title)}</strong></a><div class="muted">${escapeHtml(book.author)}</div><div>${book.tags.map((tag) => `<span class="chip-sm">${escapeHtml(tag.name)}</span>`).join(" ")}</div></div>
    <button class="btn btn-danger btn-xs" data-remove-favorite="${book.id}">取消收藏</button>
  </article>`,
      )
      .join("") || '<div class="empty">还没有收藏图书</div>';
  target.querySelectorAll("[data-remove-favorite]").forEach((button) => {
    button.onclick = async () => {
      if (!window.confirm("确定取消收藏这本书吗？")) return;
      await request("/favorites", {
        method: "DELETE",
        body: JSON.stringify({
          book_id: Number(button.dataset.removeFavorite),
        }),
      });
      await loadFavorites(page);
    };
  });
  const pager = document.querySelector("#favoritePager");
  pager.innerHTML =
    data.pages > 1
      ? `<div class="pager"><button class="btn btn-outline" data-page="${page - 1}" ${page <= 1 ? "disabled" : ""}>上一页</button><span class="muted">第 ${page} / ${data.pages} 页</span><button class="btn btn-outline" data-page="${page + 1}" ${page >= data.pages ? "disabled" : ""}>下一页</button></div>`
      : "";
  pager
    .querySelectorAll("[data-page]")
    .forEach(
      (button) =>
        (button.onclick = () => loadFavorites(Number(button.dataset.page))),
    );
}

if (window.BRS.page === "favorites") loadFavorites();
