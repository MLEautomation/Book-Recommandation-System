import { escapeHtml, request } from "./api.js";

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

function renderResults(data) {
  document.querySelector("#qaKeywords").innerHTML = data.keywords
    .map(
      (keyword) =>
        `<span class="chip-sm">${escapeHtml(keyword.type)} · ${escapeHtml(keyword.name)} ${keyword.weight}</span>`,
    )
    .join("");
  document.querySelector("#qaBooks").innerHTML =
    data.items
      .map(
        (book) =>
          `<article class="bcard"><a href="/book/${book.id}">${coverMarkup(book)}</a><div class="btitle"><a href="/book/${book.id}">${escapeHtml(book.title)}</a></div><div class="bauthor">${escapeHtml(book.author)}</div><div class="book-meta">${metaMarkup(book)}</div></article>`,
      )
      .join("") || '<div class="empty">没有找到匹配图书</div>';
  document.querySelector("#qaRecommendations").hidden = false;
}

document.querySelector("#qaForm").onsubmit = async (event) => {
  event.preventDefault();
  const prompt = document.querySelector("#qaPrompt").value.trim();
  const status = document.querySelector("#qaStatus");
  const submit = document.querySelector("#qaSubmit");
  if (!prompt) {
    status.textContent = "请输入你的阅读偏好";
    return;
  }
  submit.disabled = true;
  status.textContent = "正在分析标签并检索图书…";
  try {
    const data = await request("/qa/recommend", {
      method: "POST",
      body: JSON.stringify({ prompt }),
    });
    renderResults(data);
    status.textContent = `${data.message || "问答推荐完成"}。识别出 ${data.keywords.length} 个标签，初筛 ${data.candidate_total ?? data.total} 本，最终推荐 ${data.total} 本`;
  } catch (error) {
    status.textContent = error.message;
  } finally {
    submit.disabled = false;
  }
};
