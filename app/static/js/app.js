window.BRS = { page: null };
const api = async (path, opt = {}) => {
  const r = await fetch("/api" + path, {
    headers: { "Content-Type": "application/json" },
    ...opt,
  });
  const d = await r.json();
  if (!r.ok) throw Error(d.error || "请求失败");
  return d;
};
const toast = (s) => {
  const x = document.querySelector("#toast");
  x.textContent = s;
  x.style.display = "block";
  setTimeout(() => (x.style.display = "none"), 2500);
};
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const coverMarkup = (book) => {
  const url = book.cover_path
    ? book.cover_path.startsWith("//")
      ? "https:" + book.cover_path
      : book.cover_path
    : "";
  return `<div class="cover">${url ? `<img src="${esc(url)}" alt="${esc(book.title)}封面" loading="lazy">` : ""}<span class="init">${esc(book.title.slice(0, 1))}</span></div>`;
};
const bookMetaMarkup = (book) => {
  const tags = Object.fromEntries(
    (book.tags || []).map((tag) => [tag.type, tag.name]),
  );
  return [
    ["类型", tags["类型"]],
    ["篇幅", tags["篇幅"] && tags["篇幅"] !== "未标注" ? tags["篇幅"] : ""],
  ]
    .filter(([, value]) => value)
    .map(
      ([label, value]) =>
        `<div class="book-meta-row"><span>${label}：</span>${esc(value)}</div>`,
    )
    .join("");
};
async function toggleFavorite(button) {
  const bookId = Number(button.dataset.fav);
  const isFavorite = button.dataset.favorite === "true";
  try {
    await api("/favorites", {
      method: isFavorite ? "DELETE" : "POST",
      body: JSON.stringify({ book_id: bookId }),
    });
    button.dataset.favorite = String(!isFavorite);
    button.classList.toggle("on", !isFavorite);
    button.textContent = !isFavorite ? "★ 已收藏" : "☆ 收藏";
    toast(!isFavorite ? "已收藏" : "已取消收藏");
  } catch (error) {
    toast(error.message);
  }
}
let homePage = 1;
let recommendOffset = 0;
let currentBookId = null;
let currentCommentSort = "hot";
let rankingType = "hot";
let rankingPageNumber = 1;
const stateStorageKey = "brs_page_state";
function readPageState() {
  try {
    return JSON.parse(sessionStorage.getItem(stateStorageKey) || "{}");
  } catch (e) {
    return {};
  }
}
function writePageState(state) {
  sessionStorage.setItem(stateStorageKey, JSON.stringify(state));
}
function saveCurrentPageState() {
  const state = readPageState();
  if (BRS.page === "home") {
    state.home = {
      tags: [...document.querySelectorAll("[data-tag].active")].map(
        (x) => x.dataset.tag,
      ),
      page: homePage,
      recommendOffset,
      scrollY: window.scrollY,
    };
  }
  if (BRS.page === "book" && currentBookId) {
    state.book = state.book || {};
    state.book[currentBookId] = {
      sort: currentCommentSort,
      scrollY: window.scrollY,
    };
  }
  writePageState(state);
}
window.addEventListener("pagehide", saveCurrentPageState);
async function nav() {
  try {
    const d = await api("/session");
    const navBar = document.querySelector("nav");
    const logoutButton = document.querySelector("#logoutBtn");
    const existingAdminLink = document.querySelector("#adminLink");
    if (d.user) {
      loginLink.hidden = true;
      registerLink.hidden = true;
      profileLink.hidden = false;
      favoritesLink.hidden = false;
      myCommentsLink.hidden = false;
      logoutButton.hidden = false;
      if (d.user.role === 1 && !existingAdminLink) {
        const adminLink = document.createElement("a");
        adminLink.href = "/admin";
        adminLink.id = "adminLink";
        adminLink.textContent = "管理";
        navBar.insertBefore(adminLink, logoutButton);
      }
      logoutButton.onclick = async () => {
        await api("/auth/logout", { method: "POST" });
        location = "/";
      };
    } else {
      loginLink.hidden = false;
      registerLink.hidden = false;
      profileLink.hidden = true;
      favoritesLink.hidden = true;
      myCommentsLink.hidden = true;
      existingAdminLink?.remove();
      logoutButton.hidden = true;
    }
  } catch (e) {}
}
async function home() {
  const s = await api("/session");
  const saved = readPageState().home || {};
  if (s.user) {
    document.querySelector("#recommendSection").hidden = false;
    recommendOffset = saved.recommendOffset || 0;
    await loadRecommendations();
    document.querySelector("#recommendMore").onclick = async () => {
      recommendOffset += 10;
      await loadRecommendations();
    };
  }
  if (saved.scrollY) setTimeout(() => window.scrollTo(0, saved.scrollY), 0);
}
function renderPager(page, pages) {
  const box = document.querySelector("#pager");
  if (!pages || pages <= 1) {
    box.innerHTML = "";
    return;
  }
  let html = `<div class="pager"><button class="btn btn-outline" data-home-page="${page - 1}" ${page <= 1 ? "disabled" : ""}>上一页</button>`;
  for (let i = 1; i <= pages; i++) {
    if (i <= 3 || i > pages - 2 || Math.abs(i - page) <= 1)
      html += `<button class="btn btn-outline${i === page ? " active" : ""}" data-home-page="${i}">${i}</button>`;
  }
  html += `<button class="btn btn-outline" data-home-page="${page + 1}" ${page >= pages ? "disabled" : ""}>下一页</button></div>`;
  box.innerHTML = html;
  box.querySelectorAll("[data-home-page]").forEach(
    (btn) =>
      (btn.onclick = () => {
        if (!btn.disabled) loadHomeBooks(Number(btn.dataset.homePage));
      }),
  );
}
async function loadHomeBooks(page) {
  homePage = page;
  const ids = [...document.querySelectorAll("[data-tag].active")].map(
    (x) => x.dataset.tag,
  );
  const query = ids.length ? "&tags=" + ids.join(",") : "";
  const b = await api("/books?page=" + page + "&size=24" + query);
  renderBooks(b);
  saveCurrentPageState();
}
function renderBooks(b) {
  document.querySelector("#books").innerHTML = b.items
    .map(
      (x) =>
        `<article class="bcard"><a href="/book/${x.id}">${coverMarkup(x)}</a><div class="btitle"><a href="/book/${x.id}">${esc(x.title)}</a></div><div class="bauthor">${esc(x.author)}</div><div class="book-meta">${bookMetaMarkup(x)}</div><div class="bfoot"><button class="fav-btn${x.is_favorite ? " on" : ""}" data-fav="${x.id}" data-favorite="${x.is_favorite}">${x.is_favorite ? "★ 已收藏" : "☆ 收藏"}</button></div></article>`,
    )
    .join("");
  document.querySelector("#bookTotal").textContent = `共 ${b.total} 本`;
  renderPager(b.page, b.pages);
  document.querySelectorAll("[data-fav]").forEach((button) => {
    button.onclick = () => toggleFavorite(button);
  });
}
async function loadRecommendations() {
  const r = await api("/recommend?offset=" + recommendOffset);
  document.querySelector("#recommendBooks").innerHTML =
    r.items
      .map(
        (x) =>
          `<article class="bcard"><a href="/book/${x.id}">${coverMarkup(x)}</a><div class="btitle"><a href="/book/${x.id}">${esc(x.title)}</a></div><div class="bauthor">${esc(x.author)}</div><div class="book-meta">${bookMetaMarkup(x)}</div><button class="fav-btn${x.is_favorite ? " on" : ""}" data-fav="${x.id}" data-favorite="${x.is_favorite}">${x.is_favorite ? "★ 已收藏" : "☆ 收藏"}</button></article>`,
      )
      .join("") || '<div class="empty">暂无更多推荐</div>';
  document.querySelector("#recommendMore").disabled =
    recommendOffset + 10 >= r.total;
  document.querySelectorAll("#recommendBooks [data-fav]").forEach((button) => {
    button.onclick = () => toggleFavorite(button);
  });
  saveCurrentPageState();
}
async function homeFiltered() {
  await loadHomeBooks(1);
}
async function login() {
  loginForm.onsubmit = async (e) => {
    e.preventDefault();
    const f = new FormData(loginForm);
    try {
      await api("/auth/login", {
        method: "POST",
        body: JSON.stringify(Object.fromEntries(f)),
      });
      location = "/";
    } catch (x) {
      toast(x.message);
    }
  };
}
async function register() {
  const cap = await api("/captcha");
  document.querySelector("#captchaText").textContent = cap.code;
  document.querySelector("#registerForm").onsubmit = async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    try {
      await api("/auth/register", {
        method: "POST",
        body: JSON.stringify(Object.fromEntries(f)),
      });
      toast("注册成功");
      setTimeout(() => (location = "/login"), 500);
    } catch (x) {
      toast(x.message);
    }
  };
}
async function rankingPage() {
  const labels = {
    hot: "按收藏量和点赞量综合排序",
    favorite: "按收藏量排序",
    like: "按点赞量排序",
    discuss: "按评论数量排序",
    worst: "按点踩量排序",
  };
  const metricLabels = {
    hot: "热度",
    favorite: "收藏",
    like: "点赞",
    discuss: "评论",
    worst: "点踩",
  };
  const tabs = document.querySelectorAll("[data-ranking-type]");
  const rankingBox = document.querySelector("#ranking");
  const pagerBox = document.querySelector("#rankingPager");
  const note = document.querySelector("#rankingNote");

  function renderRankingPager(page, pages) {
    if (!pages || pages <= 1) {
      pagerBox.innerHTML = "";
      return;
    }
    let html = `<div class="pager"><button class="btn btn-outline" data-ranking-page="${page - 1}" ${page <= 1 ? "disabled" : ""}>上一页</button>`;
    for (let i = 1; i <= pages; i += 1) {
      if (i <= 3 || i > pages - 2 || Math.abs(i - page) <= 1) {
        html += `<button class="btn btn-outline${i === page ? " active" : ""}" data-ranking-page="${i}">${i}</button>`;
      }
    }
    html += `<button class="btn btn-outline" data-ranking-page="${page + 1}" ${page >= pages ? "disabled" : ""}>下一页</button></div>`;
    pagerBox.innerHTML = html;
    pagerBox.querySelectorAll("[data-ranking-page]").forEach((button) => {
      button.onclick = () => {
        if (!button.disabled) loadRanking(Number(button.dataset.rankingPage));
      };
    });
  }

  async function loadRanking(page = 1) {
    rankingPageNumber = page;
    rankingBox.textContent = "加载中…";
    try {
      const d = await api(
        `/ranking?type=${encodeURIComponent(rankingType)}&page=${page}`,
      );
      note.textContent = `${labels[rankingType]}，共 ${d.total} 本图书`;
      rankingBox.innerHTML = d.items.length
        ? d.items
            .map((item, index) => {
              const rank = (d.page - 1) * 10 + index + 1;
              return `<div class="list-row"><b>${rank}.</b><a href="/book/${item.book.id}">${esc(item.book.title)}</a><span class="muted">${metricLabels[rankingType]} ${item.metric}</span></div>`;
            })
            .join("")
        : '<div class="empty">暂无榜单数据</div>';
      renderRankingPager(d.page, d.pages);
    } catch (error) {
      rankingBox.innerHTML = `<div class="empty">${esc(error.message)}</div>`;
      pagerBox.innerHTML = "";
    }
  }

  tabs.forEach((tab) => {
    tab.onclick = () => {
      rankingType = tab.dataset.rankingType;
      rankingPageNumber = 1;
      tabs.forEach((item) => item.classList.toggle("active", item === tab));
      loadRanking(1);
    };
  });
  await loadRanking(rankingPageNumber);
}
async function loadComments(bookId, sort = "hot") {
  currentCommentSort = sort;
  const c = await api("/books/" + bookId + "/comments?sort=" + sort);
  const folded = JSON.parse(
    sessionStorage.getItem("brs_folded_comments") || "{}",
  );
  document.querySelector("#comments").innerHTML =
    [...c.normal, ...c.pinned]
      .map((x) =>
        folded[x.id]
          ? `<div id="comment-${x.id}" class="comment folded-comment"><span class="muted">评论已折叠</span><button class="btn btn-outline btn-xs" data-unfold-comment="${x.id}">展开</button></div>`
          : `<div id="comment-${x.id}" class="comment"><div class="avatar">${esc(String(x.username || "未知用户").slice(0, 1))}</div><div><b>${esc(x.username || "未知用户")}</b><div class="comment-content">${esc(x.content)}</div><div class="comment-actions"><button class="btn btn-outline btn-xs" data-fold-comment="${x.id}">折叠</button>${x.is_mine ? `<button class="btn btn-danger btn-xs" data-delete-comment="${x.id}">撤回</button>` : ""}<button class="btn btn-outline btn-xs${x.my_attitude === 1 ? " active like" : ""}" data-comment-attitude="${x.id}" data-type="1">赞 ${x.likes}</button><button class="btn btn-outline btn-xs${x.my_attitude === 2 ? " active dis" : ""}" data-comment-attitude="${x.id}" data-type="2">踩 ${x.dislikes}</button></div></div></div>`,
      )
      .join("") || "暂无评论";
  document.querySelectorAll("[data-fold-comment]").forEach(
    (btn) =>
      (btn.onclick = async () => {
        const values = JSON.parse(
          sessionStorage.getItem("brs_folded_comments") || "{}",
        );
        values[btn.dataset.foldComment] = true;
        sessionStorage.setItem("brs_folded_comments", JSON.stringify(values));
        await loadComments(bookId, sort);
      }),
  );
  document.querySelectorAll("[data-unfold-comment]").forEach(
    (btn) =>
      (btn.onclick = async () => {
        const values = JSON.parse(
          sessionStorage.getItem("brs_folded_comments") || "{}",
        );
        delete values[btn.dataset.unfoldComment];
        sessionStorage.setItem("brs_folded_comments", JSON.stringify(values));
        await loadComments(bookId, sort);
      }),
  );
  document.querySelectorAll("[data-delete-comment]").forEach(
    (btn) =>
      (btn.onclick = async () => {
        if (!window.confirm("撤回后评论及其回复会被删除，确定继续吗？")) return;
        try {
          await api("/comments/" + btn.dataset.deleteComment, {
            method: "DELETE",
          });
          await loadComments(bookId, sort);
        } catch (e) {
          toast(e.message);
        }
      }),
  );
  document.querySelectorAll("[data-comment-attitude]").forEach(
    (btn) =>
      (btn.onclick = async () => {
        try {
          await api("/comments/" + btn.dataset.commentAttitude + "/attitude", {
            method: "POST",
            body: JSON.stringify({ type: Number(btn.dataset.type) }),
          });
          await loadComments(bookId, sort);
        } catch (e) {
          toast(e.message);
        }
      }),
  );
}
async function bookPage() {
  const root = document.querySelector("#book"),
    id = root.dataset.id;
  currentBookId = id;
  const saved = (readPageState().book || {})[id] || {};
  const d = await api("/books/" + id);
  const sourceUrl = d.book.url
    ? d.book.url.startsWith("//")
      ? "https:" + d.book.url
      : d.book.url
    : "";
  root.innerHTML = `<div class="detail-top">${coverMarkup(d.book)}<div class="detail-info"><h1>${esc(d.book.title)}</h1><p>${esc(d.book.author)} · ${esc(d.book.publisher || "—")}</p><div class="tag-groups">${d.book.tags.map((x) => `<span class="chip-sm">${esc(x.type)} · ${esc(x.name)}</span>`).join(" ")}</div><p>${esc(d.book.summary || "暂无简介")}</p><div class="detail-actions"><button class="fav-btn${d.book.is_favorite ? " on" : ""}" data-fav="${d.book.id}" data-favorite="${d.book.is_favorite}">${d.book.is_favorite ? "★ 已收藏" : "☆ 收藏"}</button><button class="btn btn-outline${d.book.my_attitude === 1 ? " active like" : ""}" id="bookLike">赞 ${d.book.likes || 0}</button><button class="btn btn-outline${d.book.my_attitude === 2 ? " active dis" : ""}" id="bookDislike">踩 ${d.book.dislikes || 0}</button>${sourceUrl ? `<a class="btn btn-outline" href="${esc(sourceUrl)}" target="_blank" rel="noopener">访问原书页面</a>` : ""}</div></div></div>`;
  document.querySelectorAll("#book [data-fav]").forEach((button) => {
    button.onclick = () => toggleFavorite(button);
  });
  document.querySelector("#bookLike").onclick = async () => {
    try {
      await api("/books/" + id + "/attitude", {
        method: "POST",
        body: JSON.stringify({ type: 1 }),
      });
      saveCurrentPageState();
      location.reload();
    } catch (e) {
      toast(e.message);
    }
  };
  document.querySelector("#bookDislike").onclick = async () => {
    try {
      await api("/books/" + id + "/attitude", {
        method: "POST",
        body: JSON.stringify({ type: 2 }),
      });
      saveCurrentPageState();
      location.reload();
    } catch (e) {
      toast(e.message);
    }
  };
  let sort = saved.sort || "hot";
  await loadComments(id, sort);
  document.querySelectorAll("[data-sort]").forEach(
    (btn) =>
      (btn.onclick = async () => {
        sort = btn.dataset.sort;
        await loadComments(id, sort);
        saveCurrentPageState();
      }),
  );
  document.querySelector("#commentForm").innerHTML =
    '<textarea id="newComment" rows="3" placeholder="登录后发表评论"></textarea><br><button class="btn btn-primary" id="sendComment">发表评论</button>';
  document.querySelector("#sendComment").onclick = async () => {
    try {
      await api("/books/" + id + "/comments", {
        method: "POST",
        body: JSON.stringify({
          content: document.querySelector("#newComment").value,
        }),
      });
      saveCurrentPageState();
      location.reload();
    } catch (e) {
      toast(e.message);
    }
  };
  if (saved.scrollY) setTimeout(() => window.scrollTo(0, saved.scrollY), 0);
  if (location.hash)
    setTimeout(
      () =>
        document
          .querySelector(location.hash)
          ?.scrollIntoView({ block: "center" }),
      0,
    );
}
async function profilePage() {
  try {
    const d = await api("/me/profile");
    document.querySelector("#profile").innerHTML =
      `<h2>${esc(d.user.username)}</h2><p>${esc(d.user.email)}</p><p>注册时间 ${d.user.created_at}</p>`;
  } catch (e) {
    toast(e.message);
  }
}
async function adminPage() {
  const target = document.querySelector("#admin");
  async function loadUsers() {
    try {
      const d = await api("/admin/users");
      target.innerHTML = d.items
        .map(
          (user) =>
            `<div class="list-row"><span>${esc(user.username)} · ${esc(user.email)} · ${esc(user.status)}</span>${user.role === 1 ? "" : `<button class="btn btn-outline btn-xs" data-admin-user="${user.id}" data-admin-action="${user.status === "banned" ? "unban" : "ban"}">${user.status === "banned" ? "解封" : "封禁"}</button>`}</div>`,
        )
        .join("");
      target.querySelectorAll("[data-admin-user]").forEach((button) => {
        button.onclick = async () => {
          const action = button.dataset.adminAction;
          const message = action === "ban" ? "确定封禁该用户吗？" : "确定解封该用户吗？";
          if (!window.confirm(message)) return;
          try {
            await api(`/admin/users/${button.dataset.adminUser}/${action}`, {
              method: "POST",
            });
            await loadUsers();
          } catch (error) {
            toast(error.message);
          }
        };
      });
    } catch (error) {
      toast(error.message);
    }
  }
  async function loadComments() {
    try {
      const d = await api("/admin/comments");
      target.innerHTML =
        d.items
          .map(
            (comment) =>
              `<div class="list-row"><span>${esc(comment.username)}：${esc(comment.content)}</span><button class="btn btn-danger btn-xs" data-admin-comment="${comment.id}">删除</button></div>`,
          )
          .join("") || '<div class="empty">暂无评论</div>';
      target.querySelectorAll("[data-admin-comment]").forEach((button) => {
        button.onclick = async () => {
          if (!window.confirm("删除评论及其回复吗？")) return;
          await api(`/admin/comments/${button.dataset.adminComment}`, {
            method: "DELETE",
          });
          await loadComments();
        };
      });
    } catch (error) {
      toast(error.message);
    }
  }
  document.querySelector("#usersTab").onclick = loadUsers;
  document.querySelector("#commentsTab").onclick = loadComments;
  await loadUsers();
}
async function importPage() {
  document.querySelector("#importForm").onsubmit = async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    try {
      const r = await fetch("/api/admin/import", { method: "POST", body: f });
      const d = await r.json();
      if (!r.ok) throw Error(d.error);
      document.querySelector("#report").textContent = JSON.stringify(
        d.report,
        null,
        2,
      );
    } catch (x) {
      toast(x.message);
    }
  };
}
document.addEventListener("DOMContentLoaded", () => {
  nav();
  if (BRS.page === "home") home();
  if (BRS.page === "login") login();
  if (BRS.page === "register") register();
  if (BRS.page === "ranking") rankingPage();
  if (BRS.page === "book") bookPage();
  if (BRS.page === "profile") profilePage();
  if (BRS.page === "admin") adminPage();
  if (BRS.page === "import") importPage();
});
