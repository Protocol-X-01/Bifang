import { useState, useEffect, useRef } from 'react';
import { workspaceTree, workspaceFile, type WorkspaceFile } from '../api/workspaces';
import { FolderOpen, File, ChevronRight, ChevronDown, Search, RefreshCw } from 'lucide-react';
import { useWorkspaceStore } from '../stores/bifangStore';
import { FileViewer } from './FileViewer';

interface FileNode {
  name: string;
  path: string;
  type: 'file' | 'directory';
  children?: FileNode[];
  expanded?: boolean;
  hasChanges?: boolean;
}

export function FileExplorer() {
  const [tree, setTree] = useState<FileNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState('');
  const [error, setError] = useState('');
  const [preview, setPreview] = useState<WorkspaceFile | null>(null);
  const [previewError, setPreviewError] = useState('');
  const previewBusyPath = useRef('');
  const requestSerial = useRef(0);
  const workspacePath = useWorkspaceStore((state) => state.activeWorkspacePath);

  const loadTree = async () => {
    const serial = ++requestSerial.current;
    setTree([]);
    setError('');
    if (!workspacePath) { setLoading(false); return; }
    setLoading(true);
    try {
      const result = await workspaceTree(workspacePath);
      if (serial === requestSerial.current) setTree(JSON.parse(result));
    } catch (e) {
      if (serial === requestSerial.current) setError(e instanceof Error ? e.message : 'Could not load workspace files.');
    } finally {
      if (serial === requestSerial.current) setLoading(false);
    }
  };

  useEffect(() => {
    loadTree();
    return () => { requestSerial.current += 1; };
  }, [workspacePath]);

  const toggleNode = (node: FileNode, nodes: FileNode[]): FileNode[] => {
    return nodes.map((n) =>
      n === node ? { ...n, expanded: !n.expanded } : n.children ? { ...n, children: toggleNode(node, n.children) } : n
    );
  };

  const handleToggle = (node: FileNode) => {
    setTree(toggleNode(node, tree));
  };

  const handleOpenFile = async (node: FileNode) => {
    if (!workspacePath) return;
    previewBusyPath.current = node.path;
    setPreviewError('');
    try {
      const file = await workspaceFile(workspacePath, node.path);
      if (previewBusyPath.current === node.path) {
        setPreview(file);
        previewBusyPath.current = '';
      }
    } catch (e) {
      if (previewBusyPath.current === node.path) {
        setPreviewError(e instanceof Error ? e.message : 'Could not open the file.');
        previewBusyPath.current = '';
      }
    }
  };

  const renderNode = (node: FileNode, depth: number = 0): React.ReactElement | null => {
    const indent = depth * 16;
    const isFile = node.type === 'file';
    const hasChildren = node.type === 'directory' && node.children && node.children.length > 0;
    const matchesFilter = !filter || node.name.toLowerCase().includes(filter.toLowerCase());

    if (!matchesFilter && !(hasChildren && node.children?.some(c => c.name.toLowerCase().includes(filter.toLowerCase())))) {
      return null;
    }

    return (
      <div key={node.path} style={{ marginLeft: indent }}>
        <div
          className={`flex items-center gap-1 px-2 py-1.5 rounded hover:bg-bifang-panel-hover ${isFile ? 'cursor-pointer' : 'cursor-pointer'} transition-colors`}
          onClick={() => (isFile ? handleOpenFile(node) : hasChildren && handleToggle(node))}
          title={isFile ? `Open ${node.name}` : hasChildren ? undefined : node.name}
          role={isFile ? 'button' : undefined}
          aria-label={isFile ? `Open file ${node.name}` : undefined}
          tabIndex={isFile ? 0 : undefined}
          onKeyDown={isFile ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); void handleOpenFile(node); } } : undefined}
        >
          {hasChildren ? (
            <button className="p-1 rounded hover:bg-bifang-surface" onClick={(e) => { e.stopPropagation(); handleToggle(node); }}>
              {node.expanded ? <ChevronDown className="w-4 h-4 text-bifang-text-secondary" /> : <ChevronRight className="w-4 h-4 text-bifang-text-secondary" />}
            </button>
          ) : (
            <span className="w-6" />
          )}
          {node.type === 'directory' ? (
            <FolderOpen className="w-4 h-4 text-bifang-brand-orange flex-shrink-0" />
          ) : (
            <File className={`w-4 h-4 flex-shrink-0 ${node.hasChanges ? 'text-bifang-warning' : 'text-bifang-text-muted'}`} />
          )}
          <span className={`truncate text-body-sm ${node.hasChanges ? 'text-bifang-warning font-medium' : 'text-bifang-text-secondary'}`}>
            {node.name}
          </span>
          {node.hasChanges && <span className="ml-auto text-caption text-bifang-warning">●</span>}
        </div>
        {hasChildren && node.expanded && (
          <div>
            {node.children?.map(renderNode)}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="sidebar flex flex-col h-full bg-bifang-surface border-r border-bifang-border">
      <div className="p-4 border-b border-bifang-border">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-h5 text-bifang-text-primary">Files</h3>
          <button className="p-1.5 rounded hover:bg-bifang-panel-hover transition-colors" onClick={loadTree} disabled={loading} title="Refresh" aria-label="Refresh file tree">
            <RefreshCw className={`w-4 h-4 text-bifang-text-secondary ${loading ? 'animate-spin text-bifang-brand-orange' : ''}`} />
          </button>
        </div>
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-4 h-4 text-bifang-text-muted" />
          <input
            type="text"
            placeholder="Filter files..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="input input-sm w-full pl-8 pr-2 bg-bifang-panel border-bifang-border text-bifang-text-primary placeholder-bifang-text-muted focus:border-bifang-brand-orange focus:ring-bifang-focus-ring focus:ring-offset-bifang-focus-offset"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-2 scrollbar-thin">
        {tree.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-bifang-text-muted">
            <FolderOpen className="w-12 h-12 mb-4 opacity-50" />
            <p className="text-body-sm" role={error ? 'alert' : undefined}>{error || (loading ? 'Loading files…' : workspacePath ? 'Workspace is empty' : 'No workspace opened')}</p>
            {!error && !loading && <p className="text-caption">{workspacePath ? 'Ready for your first project files' : 'Open or create a workspace in the sidebar'}</p>}
          </div>
        ) : (
          <div className="space-y-1">
            {tree.map(renderNode)}
          </div>
        )}
        {previewError && (
          <div className="mx-2 mb-2 rounded border border-bifang-warning/40 bg-bifang-surface px-3 py-2 text-caption text-bifang-warning" role="alert">
            {previewError}
          </div>
        )}
      </div>
      {preview && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-6"
          onClick={() => setPreview(null)}
          aria-label="File preview"
        >
          <div
            className="flex h-[80vh] w-[min(960px,90vw)] flex-col overflow-hidden rounded-xl border border-bifang-border bg-bifang-panel shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <FileViewer file={preview} onClose={() => setPreview(null)} />
          </div>
        </div>
      )}
    </div>
  );
}