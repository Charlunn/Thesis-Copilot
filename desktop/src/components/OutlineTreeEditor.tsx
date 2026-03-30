import type { ConfirmedOutlineNode, ConfirmedOutlineTree, PromptPreviewResponse } from "../types";
import PromptPreviewCard from "./PromptPreviewCard";

interface OutlineTreeEditorProps {
  tree: ConfirmedOutlineTree | null;
  promptPreview: PromptPreviewResponse | null;
  onChange: (tree: ConfirmedOutlineTree) => void;
  onSave: () => void;
  onImport: () => void;
  onGeneratePrompt: () => void;
  onOpenSnapshot?: (path: string) => void;
  importDisabled: boolean;
  generatePromptDisabled: boolean;
  saveDisabled: boolean;
  editingDisabled?: boolean;
  rawText: string;
  onRawTextChange: (value: string) => void;
}

function OutlineTreeEditor({
  tree,
  promptPreview,
  onChange,
  onSave,
  onImport,
  onGeneratePrompt,
  onOpenSnapshot,
  importDisabled,
  generatePromptDisabled,
  saveDisabled,
  editingDisabled = false,
  rawText,
  onRawTextChange,
}: OutlineTreeEditorProps) {
  return (
    <section className="card wide-card">
      <div className="section-head">
        <div>
          <p className="section-kicker">Step 6</p>
          <h2>大纲导入与确认</h2>
        </div>
        <div className="mini-actions">
          <button
            className="ghost-button"
            disabled={generatePromptDisabled}
            onClick={onGeneratePrompt}
          >
            生成大纲 Prompt
          </button>
          <button className="primary-button" disabled={importDisabled} onClick={onImport}>
            导入大纲 JSON
          </button>
          <button className="secondary-button" disabled={saveDisabled} onClick={onSave}>
            保存确认版大纲
          </button>
        </div>
      </div>

      <p className="note">
        当 PDF 数量达到最低要求后，可以先生成大纲 Prompt 发给 NotebookLM，再把返回的大纲 JSON
        粘贴到这里。导入后支持继续编辑标题、增删节点、调整顺序，以及设置“单独成块”标记。
      </p>

      <PromptPreviewCard preview={promptPreview} onOpenSnapshot={onOpenSnapshot} />

      <textarea
        rows={10}
        value={rawText}
        onChange={(event) => onRawTextChange(event.target.value)}
        placeholder="在这里粘贴大纲 JSON..."
      />

      {tree ? (
        <div className="outline-editor">
          <div className="section-head">
            <label className="outline-title-field">
              论文标题
              <input
                value={tree.title}
                disabled={editingDisabled}
                onChange={(event) =>
                  onChange({
                    ...tree,
                    title: event.target.value,
                  })
                }
              />
            </label>
            <div className="mini-actions">
              <button
                className="ghost-button"
                disabled={editingDisabled}
                onClick={() => onChange(addRootNode(tree))}
              >
                新增一级节点
              </button>
            </div>
          </div>

          <div className="outline-tree">
            {tree.outline.map((node, index) => (
              <OutlineNodeEditor
                key={node.id}
                node={node}
                path={[index]}
                index={index}
                siblingCount={tree.outline.length}
                editingDisabled={editingDisabled}
                onTreeChange={onChange}
                tree={tree}
              />
            ))}
          </div>
        </div>
      ) : (
        <p className="empty-state">还没有导入大纲。达到最低 PDF 数量后即可开始这一步。</p>
      )}
    </section>
  );
}

function OutlineNodeEditor({
  tree,
  node,
  path,
  index,
  siblingCount,
  editingDisabled,
  onTreeChange,
}: {
  tree: ConfirmedOutlineTree;
  node: ConfirmedOutlineNode;
  path: number[];
  index: number;
  siblingCount: number;
  editingDisabled: boolean;
  onTreeChange: (tree: ConfirmedOutlineTree) => void;
}) {
  return (
    <div className="outline-node">
      <div className="outline-node-head">
        <div className="outline-node-meta">
          <span className="outline-node-id">
            {node.id} · L{node.level}
          </span>
          <input
            value={node.title}
            disabled={editingDisabled}
            onChange={(event) =>
              onTreeChange(
                updateNodeAtPath(tree, path, (currentNode) => ({
                  ...currentNode,
                  title: event.target.value,
                })),
              )
            }
          />
        </div>
        <div className="outline-node-flags">
          <label className="outline-check">
            <input
              type="checkbox"
              checked={node.enabled}
              disabled={editingDisabled}
              onChange={(event) =>
                onTreeChange(
                  updateNodeAtPath(tree, path, (currentNode) => ({
                    ...currentNode,
                    enabled: event.target.checked,
                  })),
                )
              }
            />
            <span>启用</span>
          </label>
          <label className="outline-check">
            <input
              type="checkbox"
              checked={node.must_be_separate_block}
              disabled={editingDisabled}
              onChange={(event) =>
                onTreeChange(
                  updateNodeAtPath(tree, path, (currentNode) => ({
                    ...currentNode,
                    must_be_separate_block: event.target.checked,
                  })),
                )
              }
            />
            <span>单独成块</span>
          </label>
        </div>
      </div>

      <div className="mini-actions outline-node-actions">
        <button
          className="ghost-button"
          disabled={editingDisabled || index === 0}
          onClick={() => onTreeChange(moveNode(tree, path, -1))}
        >
          上移
        </button>
        <button
          className="ghost-button"
          disabled={editingDisabled || index >= siblingCount - 1}
          onClick={() => onTreeChange(moveNode(tree, path, 1))}
        >
          下移
        </button>
        <button
          className="ghost-button"
          disabled={editingDisabled}
          onClick={() => onTreeChange(addSiblingNode(tree, path))}
        >
          新增同级
        </button>
        <button
          className="ghost-button"
          disabled={editingDisabled}
          onClick={() => onTreeChange(addChildNode(tree, path))}
        >
          新增子级
        </button>
        <button
          className="ghost-button"
          disabled={editingDisabled}
          onClick={() => onTreeChange(deleteNode(tree, path))}
        >
          删除
        </button>
      </div>

      {node.children.length ? (
        <div className="outline-children">
          {node.children.map((child, childIndex) => (
            <OutlineNodeEditor
              key={child.id}
              tree={tree}
              node={child}
              path={[...path, childIndex]}
              index={childIndex}
              siblingCount={node.children.length}
              editingDisabled={editingDisabled}
              onTreeChange={onTreeChange}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function addRootNode(tree: ConfirmedOutlineTree) {
  return normalizeTree({
    ...tree,
    outline: [...tree.outline, createNode()],
  });
}

function addChildNode(tree: ConfirmedOutlineTree, path: number[]) {
  return normalizeTree(
    withDraftTree(tree, (draft) => {
      const node = getNodeAtPath(draft.outline, path);
      node.children.push(createNode());
    }),
  );
}

function addSiblingNode(tree: ConfirmedOutlineTree, path: number[]) {
  return normalizeTree(
    withDraftTree(tree, (draft) => {
      const siblings = getSiblingList(draft.outline, path);
      const index = path[path.length - 1];
      siblings.splice(index + 1, 0, createNode());
    }),
  );
}

function deleteNode(tree: ConfirmedOutlineTree, path: number[]) {
  return normalizeTree(
    withDraftTree(tree, (draft) => {
      const siblings = getSiblingList(draft.outline, path);
      const index = path[path.length - 1];
      siblings.splice(index, 1);
    }),
  );
}

function moveNode(tree: ConfirmedOutlineTree, path: number[], direction: -1 | 1) {
  return normalizeTree(
    withDraftTree(tree, (draft) => {
      const siblings = getSiblingList(draft.outline, path);
      const index = path[path.length - 1];
      const targetIndex = index + direction;
      if (targetIndex < 0 || targetIndex >= siblings.length) {
        return;
      }
      const [item] = siblings.splice(index, 1);
      siblings.splice(targetIndex, 0, item);
    }),
  );
}

function updateNodeAtPath(
  tree: ConfirmedOutlineTree,
  path: number[],
  updater: (node: ConfirmedOutlineNode) => ConfirmedOutlineNode,
) {
  return normalizeTree(
    withDraftTree(tree, (draft) => {
      const siblings = getSiblingList(draft.outline, path);
      const index = path[path.length - 1];
      siblings[index] = updater(siblings[index]);
    }),
  );
}

function withDraftTree(
  tree: ConfirmedOutlineTree,
  mutator: (draft: ConfirmedOutlineTree) => void,
) {
  const draft = cloneTree(tree);
  mutator(draft);
  return draft;
}

function cloneTree(tree: ConfirmedOutlineTree): ConfirmedOutlineTree {
  return {
    ...tree,
    outline: cloneNodes(tree.outline),
  };
}

function cloneNodes(nodes: ConfirmedOutlineNode[]): ConfirmedOutlineNode[] {
  return nodes.map((node) => ({
    ...node,
    children: cloneNodes(node.children),
  }));
}

function normalizeTree(tree: ConfirmedOutlineTree): ConfirmedOutlineTree {
  return {
    ...tree,
    outline: normalizeNodes(tree.outline, 1, []),
  };
}

function normalizeNodes(
  nodes: ConfirmedOutlineNode[],
  level: number,
  prefix: number[],
): ConfirmedOutlineNode[] {
  return nodes.map((node, index) => {
    const currentPath = [...prefix, index + 1];
    return {
      ...node,
      id: currentPath.join("."),
      level,
      title: node.title,
      children: normalizeNodes(node.children, level + 1, currentPath),
    };
  });
}

function getNodeAtPath(nodes: ConfirmedOutlineNode[], path: number[]) {
  let currentNodes = nodes;
  let currentNode = currentNodes[path[0]];
  for (const index of path.slice(1)) {
    currentNodes = currentNode.children;
    currentNode = currentNodes[index];
  }
  return currentNode;
}

function getSiblingList(nodes: ConfirmedOutlineNode[], path: number[]) {
  if (path.length === 1) {
    return nodes;
  }
  const parentNode = getNodeAtPath(nodes, path.slice(0, -1));
  return parentNode.children;
}

function createNode(): ConfirmedOutlineNode {
  return {
    id: "",
    level: 1,
    title: "新节点",
    enabled: true,
    must_be_separate_block: false,
    children: [],
  };
}

export default OutlineTreeEditor;
