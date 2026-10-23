import { useState, useEffect } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { FolderOpen, File, ChevronRight, ChevronDown, Search, RefreshCw } from 'lucide-react';
import { useWorkspaceStore } from '../stores/bifangStore';

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
  const workspacePath = useWorkspaceStore((state) => state.activeWorkspacePath);

  const loadTree = async () => {
    if (!workspacePath) return;
    setLoading(true);
    try {
      const result = await invoke<string>('get_file_tree', { path: workspacePath });
      setTree(JSON.parse(result));
    } catch (e) {
      console.error('Failed to load file tree:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTree();
  }, [workspacePath]);

  const toggleNode = (node: FileNode, nodes: FileNode[]): FileNode[] => {
    return nodes.map((n) =>
      n === node ? { ...n, expanded: !n.expanded } : n.children ? { ...n, children: toggleNode(node, n.children) } : n
    );
  };

  const handleToggle = (node: FileNode) => {
    setTree(toggleNode(node, tree));
  };

  const renderNode = (node: FileNode, depth: number = 0): React.ReactElement | null => {
    const indent = depth * 16;
    const hasChildren = node.type === 'directory' && node.children && node.children.length > 0;
    const matchesFilter = !filter || node.name.toLowerCase().includes(filter.toLowerCase());

    if (!matchesFilter && !(hasChildren && node.children?.some(c => c.name.toLowerCase().includes(filter.toLowerCase())))) {
      return null;
    }

    return (
      <div key={node.path} style={{ marginLeft: indent }}>
        <div
          className="flex items-center gap-1 px-2 py-1.5 rounded hover:bg-surface-800 cursor-pointer transition-colors"
          onClick={() => hasChildren && handleToggle(node)}
        >
          {hasChildren ? (
            <button className="p-1 rounded hover:bg-surface-700" onClick={(e) => { e.stopPropagation(); handleToggle(node); }}>
              {node.expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
            </button>
          ) : (
            <span className="w-6" />
          )}
          {node.type === 'directory' ? (
            <FolderOpen className="w-4 h-4 text-bifang-400 flex-shrink-0" />
          ) : (
            <File className={`w-4 h-4 flex-shrink-0 ${node.hasChanges ? 'text-yellow-400' : 'text-surface-400'}`} />
          )}
          <span className={`truncate text-sm ${node.hasChanges ? 'text-yellow-300 font-medium' : 'text-surface-300'}`}>
            {node.name}
          </span>
          {node.hasChanges && <span className="ml-auto text-xs text-yellow-400">●</span>}
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
    <div className="sidebar flex flex-col bg-surface-900 border-r border-surface-800">
      <div className="p-4 border-b border-surface-800">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-medium text-surface-100">Files</h3>
          <button className="p-1.5 rounded hover:bg-surface-800" onClick={loadTree} disabled={loading} title="Refresh">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-4 h-4 text-surface-500" />
          <input
            type="text"
            placeholder="Filter files..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="w-full pl-8 pr-2 py-1.5 bg-surface-800 border border-surface-700 rounded text-sm text-surface-100 placeholder-surface-500 focus:border-bifang-500 focus:outline-none focus:ring-1 focus:ring-bifang-500"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-2 scrollbar-thin">
        {tree.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-surface-500">
            <FolderOpen className="w-12 h-12 mb-4 opacity-50" />
            <p className="text-sm">No workspace opened</p>
            <p className="text-xs">Click folder icon in sidebar to open</p>
          </div>
        ) : (
          <div className="space-y-1">
            {tree.map(renderNode)}
          </div>
        )}
      </div>

    </div>
  );
}
