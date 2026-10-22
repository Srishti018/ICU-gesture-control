import { Radio } from "lucide-react";

export default function EmptyState() {
  return (
    <div className="empty-state" data-testid="empty-state">
      <Radio size={32} aria-hidden="true" />
      <h2>Waiting for bed devices…</h2>
      <p>Start a node or the fake node. Each bed appears here as soon as it connects.</p>
      <div className="cmds">
        <span className="label">Bed node (webcam)</span>
        <code>python -m node.main --node bed1 --vision camera --bio replay:rest</code>
        <span className="label">Fake node</span>
        <code>.venv/bin/python sim/fake_node.py --node bed2</code>
      </div>
    </div>
  );
}
