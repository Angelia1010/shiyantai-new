import request from '@/utils/request'

export function readExcelApi(query) {
  const { page, page_size = 100, file_names, path } = query || {};
  let fileNamesArray = [];
  if (Array.isArray(file_names)) {
    fileNamesArray = file_names;
  } else if (typeof file_names === 'string' && file_names.trim()) {
    fileNamesArray = [file_names];
  }
  return request({
    url: `/file/read_excel`,
    method: 'get',
    params: { page, page_size, file_names: fileNamesArray, path }
  })
}

export function newFileListAPI(path) {
  return request({
    url: `/file/new_files`,
    method: 'get',
    params: { path }
  })
}

export function setWatchPath(path) {
  return request({
    url: `/file/set_watch_path`,
    method: 'post',
    data: { path }
  })
}

export function getWatchPath() {
  return request({
    url: `/file/get_watch_path`,
    method: 'get'
  })
}

export function fileListAPI(path) {
  return request({
    url: `/file/files`,
    method: 'get',
    params: { path }
  })
}

export function getGoingJob() {
  return request({
    url: `/db/getGoingJob`,
    method: 'get',
  })
}

export function getJobStatus(taskId) {
  return request({
    url: `/db/getJobStatus`,
    method: 'get',
    params: { taskId }
  })
}

export function diagnose(task_id, path, file_name) {
  return request({
    url: `/db/diagnose`,
    method: 'get',
    params: { task_id, path, file_name }
  })
}


export async function storeReport(data) {
  console.log('storeReport', data)
  return request({
    url: `/db/store_report`,
    method: 'get',
    params: data
  })
}

export async function createTask(data) {
  console.log('createJob', data)
  return request({
    url: `/db/createJob`,
    method: 'get',
    params: data
  })
}

export async function chatStream(message, sessionId, onMessageCallback) {
  const payload = {
    question: message,
    session_id: sessionId,
    window_idx: 10,
  };
  const url = `/ai/chat`;

  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8', { fatal: true }); // 使用utf-8解码器

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value, { stream: true });
    onMessageCallback(chunk)
  }
}

export async function chatStreamWithTmdsFile(sessionId, filepath, onMessageCallback) {
  const payload = {
    session_id: sessionId,
    file_path: filepath,
  };
  const url = `/ai/analyze_json`;

  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8', { fatal: true }); // 使用utf-8解码器

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value, { stream: true });
    onMessageCallback(chunk)
  }
}

export function fetchArticle(id) {
  return request({
    url: '/vue-element-admin/article/detail',
    method: 'get',
    params: { id }
  })
}

export function fetchPv(pv) {
  return request({
    url: '/vue-element-admin/article/pv',
    method: 'get',
    params: { pv }
  })
}

export function createArticle(data) {
  return request({
    url: '/vue-element-admin/article/create',
    method: 'post',
    data
  })
}

export function updateArticle(data) {
  return request({
    url: '/vue-element-admin/article/update',
    method: 'post',
    data
  })
}



