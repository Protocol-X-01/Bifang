export function followViewportResize(viewport: HTMLElement): () => void {
  let previousHeight = viewport.clientHeight;
  let following = viewport.scrollHeight - viewport.scrollTop - previousHeight <= 32;
  const onScroll = () => {
    if (viewport.clientHeight !== previousHeight) return;
    following = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight <= 32;
  };
  const observer = new ResizeObserver(() => {
    const height = viewport.clientHeight;
    if (height === previousHeight) return;
    previousHeight = height;
    if (following && height > 0) viewport.scrollTop = viewport.scrollHeight;
  });
  viewport.addEventListener('scroll', onScroll);
  observer.observe(viewport);
  return () => {
    viewport.removeEventListener('scroll', onScroll);
    observer.disconnect();
  };
}
