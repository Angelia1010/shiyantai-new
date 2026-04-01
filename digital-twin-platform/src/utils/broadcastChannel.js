const CHANNEL_NAME = 'diagnosis_data_channel'

let channel = null

export function initBroadcastChannel() {
  if (!channel) {
    channel = new BroadcastChannel(CHANNEL_NAME)
  }
  return channel
}

export function getBroadcastChannel() {
  if (!channel) {
    return initBroadcastChannel()
  }
  return channel
}

export function sendDataToDashboard(data) {
  const ch = getBroadcastChannel()
  ch.postMessage({
    type: 'DIAGNOSIS_DATA',
    payload: data,
    timestamp: Date.now()
  })
}

export function sendStatusToDashboard(status) {
  const ch = getBroadcastChannel()
  ch.postMessage({
    type: 'DIAGNOSIS_STATUS',
    payload: status,
    timestamp: Date.now()
  })
}

export function sendFeatureMapToDashboard(featureMap) {
  const ch = getBroadcastChannel()
  ch.postMessage({
    type: 'FEATURE_MAP',
    payload: featureMap,
    timestamp: Date.now()
  })
}

export function sendDiagnosisResultToDashboard(result) {
  const ch = getBroadcastChannel()
  ch.postMessage({
    type: 'DIAGNOSIS_RESULT',
    payload: result,
    timestamp: Date.now()
  })
}

export function closeBroadcastChannel() {
  if (channel) {
    channel.close()
    channel = null
  }
}

export default {
  initBroadcastChannel,
  getBroadcastChannel,
  sendDataToDashboard,
  sendStatusToDashboard,
  sendFeatureMapToDashboard,
  sendDiagnosisResultToDashboard,
  closeBroadcastChannel
}
