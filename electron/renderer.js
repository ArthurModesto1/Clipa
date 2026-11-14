'use strict';

const $ = (id) => document.getElementById(id);
const read = (key, fallback) => {
  try {
    return JSON.parse(localStorage.getItem(key)) ?? fallback;
  } catch {
    return fallback;
  }
};
const storedString = (key) => {
  try {
    return localStorage.getItem(key) || '';
  } catch {
    return '';
  }
};
const state = {
  config: null,
  capabilities: null,
  mode: 'video',
  media: null,
  job: null,
  busy: false,
  searching: false,
  folder: storedString('clipa-folder'),
  cookies: storedString('clipa-cookies'),
  history: read('clipa-history', []),
  infoSequence: 0,
  lastFolder: '',
  pollingErrors: 0,
};
if (!Array.isArray(state.history)) state.history = [];
state.history = state.history.filter((item) => item && typeof item === 'object').slice(0, 100);

function store(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    toast('Não foi possível guardar esta preferência.');
  }
}
function toast(text) {
  $('toast').textContent = text;
  $('toast').hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => {
    $('toast').hidden = true;
  }, 4500);
}
function navigate(page) {
  document.querySelectorAll('.page').forEach((element) => {
    element.hidden = element.id !== `page-${page}`;
  });
  document.querySelectorAll('.nav-button').forEach((button) => {
    const active = button.dataset.page === page;
    button.classList.toggle('active', active);
    if (active) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  });
}
function showError(error) {
  $('messageTitle').textContent = error.message || 'Não foi possível concluir esta ação.';
  $('messageHint').textContent = error.hint || '';
  $('messageSettings').hidden = ![
    'login_required',
    'platform_blocked',
    'invalid_cookies',
    'missing_ffmpeg',
  ].includes(error.code);
  $('message').hidden = false;
}
function clearError() {
  $('message').hidden = true;
}

async function api(route, data) {
  if (!state.config) throw new Error('O Clipa ainda está iniciando. Aguarde um instante.');
  const response = await fetch(state.config.url + route, {
    method: data === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Clipa-Token': state.config.token },
    body: data === undefined ? undefined : JSON.stringify(data),
    signal: AbortSignal.timeout(route === '/info' ? 150000 : 15000),
  }).catch(() => {
    throw new Error('Sem resposta do aplicativo. Confira sua conexão ou reabra o Clipa.');
  });
  const result = await response.json().catch(() => {
    throw new Error('O aplicativo retornou uma resposta inválida. Reabra o Clipa.');
  });
  if (!response.ok || result.error) {
    throw Object.assign(new Error(result.error || 'Não foi possível concluir a ação.'), {
      code: result.code,
      hint: result.hint,
    });
  }
  return result;
}

function syncDisabled() {
  $('downloadBtn').disabled = state.busy || !state.config || !state.capabilities?.ffmpeg;
  $('fetchBtn').disabled = state.busy || state.searching || !state.config;
  $('urlInput').disabled = state.busy;
  $('qualitySelect').disabled = state.busy;
  $('formatSelect').disabled = state.busy;
  $('chooseFolder').disabled = state.busy;
  document.querySelectorAll('input[name="mode"]').forEach((input) => {
    input.disabled = state.busy;
  });
}

function setMode(mode) {
  state.mode = mode;
  const audio = mode === 'audio';
  const qualities = audio
    ? [
        ['320', '320 kbps'],
        ['256', '256 kbps'],
        ['192', '192 kbps · padrão'],
        ['128', '128 kbps'],
      ]
    : [
        ['2160', '2160p · 4K'],
        ['1440', '1440p · QHD'],
        ['1080', '1080p · Full HD'],
        ['720', '720p · HD'],
        ['480', '480p'],
        ['360', '360p'],
      ];
  const formats = audio ? ['mp3', 'aac', 'opus', 'flac', 'wav'] : ['mp4', 'mkv', 'webm'];
  $('qualitySelect').replaceChildren(
    ...qualities.map(([value, label]) => new Option(label, value))
  );
  $('formatSelect').replaceChildren(
    ...formats.map((value) => new Option(value.toUpperCase(), value))
  );
  $('qualitySelect').value = audio ? '192' : '1080';
  $('qualityLabel').textContent = audio ? 'Qualidade do áudio' : 'Resolução máxima';
  $('downloadBtn').replaceChildren();
  const icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  use.setAttribute('href', '#i-download');
  icon.append(use);
  $('downloadBtn').append(icon, document.createTextNode(audio ? 'Baixar áudio' : 'Baixar vídeo'));
  updateSummary();
}

function updateSummary() {
  const fmt = $('formatSelect').value;
  const quality = $('qualitySelect').value;
  const lossless = ['flac', 'wav'].includes(fmt);
  $('qualitySelect').disabled = state.busy || lossless;
  $('fileType').firstChild.textContent = fmt.toUpperCase();
  $('fileType')
    .querySelector('use')
    .setAttribute('href', state.mode === 'audio' ? '#i-audio' : '#i-video');
  $('summaryText').textContent =
    state.mode === 'video'
      ? `Vídeo em até ${quality}p, com imagem e som.`
      : lossless
        ? `Áudio em ${fmt.toUpperCase()}, sem compressão adicional com perdas.`
        : `Só o áudio, em ${fmt.toUpperCase()} a ${quality} kbps.`;
  $('qualityHint').textContent =
    state.mode === 'video'
      ? 'Usamos a melhor resolução disponível até o limite escolhido.'
      : lossless
        ? 'FLAC e WAV preservam a fonte disponível, sem recuperar qualidade que ela não possui.'
        : 'A qualidade final também depende do áudio original.';
}

function renderFolder() {
  const folder = state.folder || state.capabilities?.download_dir || 'Pasta de downloads';
  $('folderPath').textContent = folder;
  $('folderPath').title = folder;
  $('settingsFolder').textContent = folder;
}
async function chooseFolder() {
  try {
    const folder = await window.electron.chooseFolder();
    if (folder) {
      state.folder = folder;
      store('clipa-folder', folder);
      renderFolder();
    }
  } catch {
    toast('Não foi possível abrir o seletor de pastas.');
  }
}
function renderCookies() {
  $('cookiePath').textContent = state.cookies || 'Nenhum arquivo selecionado';
  $('clearCookies').hidden = !state.cookies;
}
async function openFolder(folder) {
  try {
    await window.electron.openFolder(folder);
  } catch {
    toast('Não foi possível abrir a pasta. Ela pode ter sido movida ou removida.');
  }
}

function resetPreview() {
  state.media = null;
  $('previewTitle').textContent = 'Pronto para o próximo play.';
  $('previewPlatform').textContent = 'Sua mídia aparece aqui';
  $('previewMeta').textContent = 'Busque um link para conferir o título e a duração.';
  $('previewThumb').hidden = true;
  $('previewThumb').removeAttribute('src');
  $('previewPlaceholder').removeAttribute('hidden');
}

async function fetchInfo(event) {
  event?.preventDefault();
  if (state.busy || state.searching || !$('urlInput').value.trim()) return;
  clearError();
  const sequence = ++state.infoSequence;
  const url = $('urlInput').value.trim();
  state.searching = true;
  syncDisabled();
  $('fetchBtn').textContent = 'Buscando…';
  try {
    const result = await api('/info', { url, cookie_file: state.cookies });
    if (sequence !== state.infoSequence || url !== $('urlInput').value.trim()) return;
    state.media = { ...result, sourceUrl: url };
    $('previewTitle').textContent = result.title;
    $('previewPlatform').textContent = result.platform;
    $('previewMeta').textContent = `${result.channel} • ${result.duration}`;
    if (result.thumbnail && /^https:\/\//i.test(result.thumbnail)) {
      $('previewThumb').src = result.thumbnail;
      $('previewThumb').hidden = false;
      $('previewPlaceholder').setAttribute('hidden', '');
    }
  } catch (error) {
    if (sequence === state.infoSequence) showError(error);
  } finally {
    state.searching = false;
    syncDisabled();
    updateSummary();
    $('fetchBtn').textContent = 'Buscar mídia';
  }
}

function detectPlatform() {
  let platform = '';
  try {
    const raw = $('urlInput').value.trim();
    const host = new URL(/^https?:\/\//.test(raw) ? raw : `https://${raw}`).hostname;
    for (const [domain, name] of [
      ['youtube.com', 'YouTube'],
      ['youtu.be', 'YouTube'],
      ['x.com', 'X'],
      ['twitter.com', 'X'],
      ['instagram.com', 'Instagram'],
      ['tiktok.com', 'TikTok'],
    ]) {
      if (host === domain || host.endsWith(`.${domain}`)) platform = name;
    }
  } catch {
    /* Keep all platform badges neutral for incomplete URLs. */
  }
  document
    .querySelectorAll('[data-platform]')
    .forEach((element) =>
      element.classList.toggle('detected', element.dataset.platform === platform)
    );
  state.infoSequence++;
  resetPreview();
}

async function startDownload() {
  if (state.busy) return;
  const url = $('urlInput').value.trim();
  if (!url) {
    $('urlInput').focus();
    showError(new Error('Cole o link que você quer baixar.'));
    return;
  }
  clearError();
  const snapshot = {
    url,
    mode: state.mode,
    quality: $('qualitySelect').value,
    format: $('formatSelect').value,
    output_dir: state.folder,
    cookie_file: state.cookies,
    download_id: 'dl_' + crypto.randomUUID().replaceAll('-', ''),
  };
  state.busy = true;
  state.infoSequence++;
  syncDisabled();
  $('progressSection').hidden = false;
  $('openFolderBtn').hidden = true;
  $('cancelBtn').hidden = true;
  $('progressLabel').textContent = 'Preparando download…';
  $('progressPercent').textContent = '';
  $('progressDetails').textContent = 'Conectando à plataforma…';
  $('progressBar').removeAttribute('value');
  $('progressSection').scrollIntoView({
    block: 'nearest',
    behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth',
  });
  try {
    const result = await api('/download', snapshot);
    state.job = { ...snapshot, download_id: result.download_id, title: state.media?.title };
    state.pollingErrors = 0;
    $('cancelBtn').hidden = false;
    $('cancelBtn').disabled = false;
    pollProgress();
  } catch (error) {
    state.busy = false;
    syncDisabled();
    updateSummary();
    $('progressSection').hidden = true;
    showError(error);
  }
}

async function pollProgress() {
  if (!state.job) return;
  try {
    const progress = await api('/progress/' + state.job.download_id);
    if (state.pollingErrors >= 3) clearError();
    state.pollingErrors = 0;
    $('progressLabel').textContent =
      {
        starting: 'Preparando download…',
        downloading: 'Baixando seu arquivo…',
        processing: 'Preparando o arquivo final…',
        done: 'Arquivo salvo. Pode dar o play.',
        cancelled: 'Download cancelado.',
        error: 'O download não foi concluído.',
      }[progress.status] || 'Preparando…';
    $('progressPercent').textContent = progress.indeterminate
      ? ''
      : `${Math.round(progress.percent || 0)}%`;
    if (progress.indeterminate) $('progressBar').removeAttribute('value');
    else $('progressBar').value = progress.percent || 0;
    $('progressDetails').textContent =
      progress.status === 'processing'
        ? 'Finalizando o formato escolhido. Isso pode levar um instante.'
        : `${progress.speed || '—'}   •   Tempo restante: ${progress.eta || '—'}`;
    $('cancelBtn').hidden = progress.status === 'processing';
    if (['done', 'error', 'cancelled'].includes(progress.status)) {
      const job = state.job;
      state.job = null;
      state.busy = false;
      syncDisabled();
      updateSummary();
      $('cancelBtn').hidden = true;
      if (progress.status === 'done') {
        state.lastFolder = progress.output_dir;
        $('openFolderBtn').hidden = false;
        $('progressDetails').textContent = 'Salvo na pasta de destino.';
        state.history.unshift({
          title: progress.title || job.title || job.url,
          url: job.url,
          quality: job.quality,
          fmt: job.format,
          mode: job.mode,
          folder: progress.output_dir,
          date: new Date().toISOString(),
        });
        state.history = state.history.slice(0, 100);
        store('clipa-history', JSON.stringify(state.history));
        renderHistory();
      } else if (progress.status === 'error') {
        showError({ message: progress.error, hint: progress.hint, code: progress.code });
        $('progressDetails').textContent = 'Confira a orientação acima e tente novamente.';
      } else
        $('progressDetails').textContent =
          'Você pode iniciar outro download. Arquivos parciais podem permanecer na pasta.';
      return;
    }
  } catch (error) {
    state.pollingErrors++;
    if (error.code === 'not_found' || error.code === 'unauthorized') {
      state.job = null;
      state.busy = false;
      syncDisabled();
      updateSummary();
      $('cancelBtn').hidden = true;
      $('progressLabel').textContent = 'Não foi possível acompanhar o download.';
      showError(error);
      return;
    }
    $('progressLabel').textContent = 'Tentando reconectar ao download…';
    if (state.pollingErrors === 3) showError(error);
  }
  setTimeout(pollProgress, state.pollingErrors ? 3000 : 700);
}

function renderHistory() {
  const list = $('historyList');
  list.replaceChildren();
  $('historyCount').textContent = state.history.length;
  $('clearHistory').disabled = !state.history.length;
  if (!state.history.length) {
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    const title = document.createElement('h2');
    title.textContent = 'Seu primeiro arquivo começa com um link.';
    const description = document.createElement('p');
    description.textContent = 'Os downloads concluídos vão aparecer aqui.';
    const button = document.createElement('button');
    button.className = 'button primary';
    button.textContent = 'Baixar um arquivo';
    button.addEventListener('click', () => {
      navigate('download');
      $('urlInput').focus();
    });
    empty.append(title, description, button);
    list.append(empty);
    return;
  }
  state.history.forEach((item) => {
    const row = $('historyTemplate').content.cloneNode(true);
    row.querySelector('h2').textContent = String(item.title || 'Arquivo');
    const date = new Date(item.date);
    const dateLabel = Number.isNaN(date.getTime())
      ? String(item.date || '')
      : date.toLocaleDateString('pt-BR');
    const quality = ['flac', 'wav'].includes(item.fmt)
      ? 'Fonte preservada'
      : `${item.quality || ''}${item.mode === 'audio' ? ' kbps' : 'p'}`;
    row.querySelector('p').textContent =
      `${dateLabel} • ${String(item.fmt || '').toUpperCase()} • ${quality}`;
    row.querySelector('use').setAttribute('href', item.mode === 'audio' ? '#i-audio' : '#i-video');
    const button = row.querySelector('button');
    button.disabled = !item.folder;
    if (!item.folder) button.title = 'Este registro antigo não contém a pasta de destino.';
    button.addEventListener('click', () => openFolder(item.folder));
    list.append(row);
  });
}

document
  .querySelectorAll('.nav-button')
  .forEach((button) => button.addEventListener('click', () => navigate(button.dataset.page)));
document
  .querySelectorAll('input[name="mode"]')
  .forEach((input) => input.addEventListener('change', () => setMode(input.value)));
$('qualitySelect').addEventListener('change', updateSummary);
$('formatSelect').addEventListener('change', updateSummary);
$('urlInput').addEventListener('input', detectPlatform);
$('linkForm').addEventListener('submit', fetchInfo);
$('downloadBtn').addEventListener('click', startDownload);
$('chooseFolder').addEventListener('click', chooseFolder);
$('settingsChooseFolder').addEventListener('click', chooseFolder);
$('openFolderBtn').addEventListener('click', () => openFolder(state.lastFolder));
$('previewThumb').addEventListener('error', () => {
  $('previewThumb').hidden = true;
  $('previewPlaceholder').removeAttribute('hidden');
});
$('cancelBtn').addEventListener('click', async () => {
  if (!state.job) return;
  $('cancelBtn').disabled = true;
  try {
    await api('/cancel/' + state.job.download_id, {});
    $('progressLabel').textContent = 'Cancelando…';
  } catch (error) {
    $('cancelBtn').disabled = false;
    showError(error);
  }
});
$('messageSettings').addEventListener('click', () => navigate('settings'));
$('clearHistory').addEventListener('click', () => {
  state.history = [];
  store('clipa-history', '[]');
  renderHistory();
  toast('Histórico limpo. Seus arquivos continuam na pasta.');
});
$('chooseCookies').addEventListener('click', async () => {
  try {
    const file = await window.electron.chooseCookieFile();
    if (file) {
      state.cookies = file;
      store('clipa-cookies', file);
      renderCookies();
      toast('Arquivo de sessão selecionado.');
    }
  } catch {
    toast('Não foi possível selecionar o arquivo de sessão.');
  }
});
$('clearCookies').addEventListener('click', () => {
  state.cookies = '';
  store('clipa-cookies', '');
  renderCookies();
});
$('cookiesHelp').addEventListener('click', () =>
  window.electron
    .openExternal('https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp')
    .catch(() => toast('Não foi possível abrir o navegador.'))
);
for (const [id, method] of [
  ['winMin', 'minimize'],
  ['winMax', 'maximize'],
  ['winClose', 'close'],
]) {
  $(id).addEventListener('click', () => window.electron?.[method]());
}

async function init() {
  document.querySelectorAll('input[name="theme"]').forEach((input) => {
    input.checked = input.value === document.documentElement.dataset.theme;
    input.addEventListener('change', () => {
      document.documentElement.dataset.theme = input.value;
      store('clipa-theme', input.value);
    });
  });
  setMode('video');
  renderFolder();
  renderCookies();
  renderHistory();
  syncDisabled();
  try {
    if (!window.electron?.getBackendConfig)
      throw new Error('Abra o Clipa pelo aplicativo: execute npm start na pasta do projeto.');
    state.config = await window.electron.getBackendConfig();
    state.capabilities = await api('/settings');
    renderFolder();
    $('dependencyStatus').replaceChildren(
      ...[
        ['FFmpeg + FFprobe', state.capabilities.ffmpeg],
        ['Node.js', state.capabilities.node],
        [`yt-dlp ${state.capabilities.yt_dlp_version}`, true],
      ].map(([name, ok]) => {
        const span = document.createElement('span');
        span.className = ok ? 'ok' : 'missing';
        span.textContent = `${ok ? '✓' : '!'} ${name}${ok ? '' : ' ausente'}`;
        return span;
      })
    );
    if (!state.capabilities.ffmpeg)
      showError({
        message: 'Falta uma ferramenta para preparar seus arquivos.',
        hint: 'Instale FFmpeg e FFprobe conforme o README e reabra o Clipa.',
        code: 'missing_ffmpeg',
      });
    else if (!state.capabilities.node)
      showError({
        message: 'Node.js não foi encontrado.',
        hint: 'Alguns vídeos do YouTube precisam dele. Instale Node.js e reabra o Clipa.',
      });
  } catch (error) {
    showError(error);
  }
  syncDisabled();
  updateSummary();
}
init();
