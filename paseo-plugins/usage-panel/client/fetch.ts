// 오류 원문은 화면에 싣지 않는다. 한도·토큰 조회 실패는 서버가 Settings → Plugins → Logs에 남기고,
// 여기서는 RPC 호출 자체가 실패한 경우만 앱 런타임 콘솔에 남긴다(그 화면은 데몬 쪽 출력만 모은다).
export async function callRpc<Output>(name: string, call: () => Promise<Output>): Promise<Output> {
  try {
    return await call();
  } catch (error) {
    console.error(`[usage-panel] ${name} failed:`, error);
    throw error;
  }
}
