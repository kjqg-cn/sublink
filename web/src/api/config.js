import request from '@/utils/request'
const SetConfig = (obj) => {
  return request.post('/set_config', obj)
}
const GetConfig = () => {
  return request.post('/get_config')
}
export {
  SetConfig,
  GetConfig
}
