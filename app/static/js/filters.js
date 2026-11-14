import { escapeHtml, request } from "./api.js";

let currentPage = 1;
const selectedTags = new Set();

function coverMarkup(book) {
  const cover = book.cover_path
    ? book.cover_path.startsWith("//")
      ? `https:${book.cover_path}`
      : book.cover_path
    : "";
  return `<div class="cover">${cover ? `<img src="${escapeHtml(cover)}" alt="${escapeHtml(book.title)}封面" loading="lazy">` : ""}<span class="init">${escapeHtml(book.title.slice(0, 1))}</span></div>`;
}

function metaMarkup(book) {
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
        `<div class="book-meta-row"><span>${label}：</span>${escapeHtml(value)}</div>`,
    )
    .join("");
}

function renderPager(page, pages) {
  const target = document.querySelector("#filterPager");
  if (!pages || pages <= 1) {
    target.innerHTML = "";
    return;
  }
  let html = `<div class="pager"><button class="btn btn-outline" data-filter-page="${page - 1}" ${page <= 1 ? "disabled" : ""}>上一页</button>`;
  for (let index = 1; index <= pages; index += 1) {
    if (index <= 3 || index > pages - 2 || Math.abs(index - page) <= 1) {
      html += `<button class="btn btn-outline${index === page ? " active" : ""}" data-filter-page="${index}">${index}</button>`;
    }
  }
  html += `<button class="btn btn-outline" data-filter-page="${page + 1}" ${page >= pages ? "disabled" : ""}>下一页</button></div>`;
  target.innerHTML = html;
  target.querySelectorAll("[data-filter-page]").forEach((button) => {
    button.onclick = () => {
      if (!button.disabled) loadBooks(Number(button.dataset.filterPage));
    };
  });
}

async function loadBooks(page = 1) {
  currentPage = page;
  const query = new URLSearchParams({
    page: String(page),
    size: "24",
    q: document.querySelector("#bookSearch").value.trim(),
  });
  if (selectedTags.size) query.set("tags", [...selectedTags].join(","));
  const data = await request(`/books?${query.toString()}`);
  document.querySelector("#filterTotal").textContent = `共 ${data.total} 本`;
  document.querySelector("#filterBooks").innerHTML =
    data.items
      .map(
        (book) =>
          `<article class="bcard"><a href="/book/${book.id}">${coverMarkup(book)}</a><div class="btitle"><a href="/book/${book.id}">${escapeHtml(book.title)}</a></div><div class="bauthor">${escapeHtml(book.author)}</div><div class="book-meta">${metaMarkup(book)}</div></article>`,
      )
      .join("") || '<div class="empty">没有符合条件的图书</div>';
  renderPager(data.page, data.pages);
}

async function loadTags() {
  const data = await request("/tags");
  document.querySelector("#filterTags").innerHTML = data.items
    .map(
      (group) =>
        `<div class="filter-row"><span class="ftype">${escapeHtml(group.name)}</span><div class="filter-vals">${group.tags.map((tag) => `<button class="chip" data-filter-tag="${tag.id}">${escapeHtml(tag.name)}</button>`).join("")}</div></div>`,
    )
    .join("");
  document.querySelectorAll("[data-filter-tag]").forEach((button) => {
    button.onclick = () => {
      const id = Number(button.dataset.filterTag);
      if (selectedTags.has(id)) {
        selectedTags.delete(id);
        button.classList.remove("active");
      } else {
        selectedTags.add(id);
        button.classList.add("active");
      }
      loadBooks(1);
    };
  });
}

document.querySelector("#bookSearchForm").onsubmit = (event) => {
  event.preventDefault();
  loadBooks(1);
};
document.querySelector("#clearFilters").onclick = () => {
  selectedTags.clear();
  document.querySelector("#bookSearch").value = "";
  document.querySelectorAll("[data-filter-tag]").forEach((button) => {
    button.classList.remove("active");
  });
  loadBooks(1);
};

Promise.all([loadTags(), loadBooks()]).catch((error) => {
  document.querySelector("#filterBooks").innerHTML =
    `<div class="empty">${escapeHtml(error.message)}</div>`;
});
