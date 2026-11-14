import { request, escapeHtml } from './api.js';
import { loadMyComments } from './comments.js';

async function loadInterests() {
  const [tags, profile] = await Promise.all([request('/tags'), request('/me/profile')]);
  const selected = new Set(profile.interest_ids);
  const target = document.querySelector('#interestTags');
  target.innerHTML = tags.items.map(type => `<div class="filter-row"><span class="ftype">${escapeHtml(type.name)}</span><div class="filter-vals">${type.tags.map(tag => `<button class="chip${selected.has(tag.id) ? ' active' : ''}" data-interest="${tag.id}">${escapeHtml(tag.name)}</button>`).join('')}</div></div>`).join('');
  target.querySelectorAll('[data-interest]').forEach(button => button.onclick = () => { button.classList.toggle('active'); });
  document.querySelector('#saveInterests').onclick = async () => {
    const interestIds = [...target.querySelectorAll('[data-interest].active')].map(button => Number(button.dataset.interest));
    await request('/me/profile', { method: 'PUT', body: JSON.stringify({ interest_ids: interestIds }) });
    document.querySelector('#interestStatus').textContent = '兴趣标签已保存';
  };
}

if (window.BRS.page === 'profile') loadInterests();
if (window.BRS.page === 'my-comments') loadMyComments();
