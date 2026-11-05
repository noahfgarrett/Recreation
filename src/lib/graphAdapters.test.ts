import { describe, expect, it } from 'vitest';
import { demoGraph } from './demoGraph';
import { hasActiveFilter, openReviewCount, toFlowEdges, toFlowNodes } from './graphAdapters';

describe('graph adapters', () => {
  it('maps graph nodes and edges to React Flow primitives', () => {
    expect(toFlowNodes(demoGraph.nodes)).toHaveLength(3);
    expect(toFlowEdges(demoGraph.edges)).toHaveLength(2);
  });

  it('counts open review items', () => {
    expect(openReviewCount(demoGraph)).toBe(1);
  });

  it('marks all nodes as matching when no filter is active', () => {
    const flowNodes = toFlowNodes(demoGraph.nodes);
    expect(flowNodes.every((n) => n.data.searchMatch === true)).toBe(true);
  });

  it('filters nodes by search query', () => {
    const flowNodes = toFlowNodes(demoGraph.nodes, { query: 'P-101', kind: null, confidence: null });
    const matching = flowNodes.filter((n) => n.data.searchMatch);
    expect(matching).toHaveLength(1);
    expect(matching[0].data.tag).toBe('P-101A');
  });

  it('filters nodes by kind', () => {
    const flowNodes = toFlowNodes(demoGraph.nodes, { query: '', kind: 'valve', confidence: null });
    const matching = flowNodes.filter((n) => n.data.searchMatch);
    expect(matching).toHaveLength(1);
    expect(matching[0].data.kind).toBe('valve');
  });

  it('filters nodes by confidence level', () => {
    const highNodes = toFlowNodes(demoGraph.nodes, { query: '', kind: null, confidence: 'high' });
    const highMatching = highNodes.filter((n) => n.data.searchMatch);
    expect(highMatching).toHaveLength(2);
    expect(highMatching.every((n) => n.data.confidence >= 0.85)).toBe(true);

    const medNodes = toFlowNodes(demoGraph.nodes, { query: '', kind: null, confidence: 'medium' });
    const medMatching = medNodes.filter((n) => n.data.searchMatch);
    expect(medMatching).toHaveLength(1);
    expect(medMatching[0].data.confidence).toBeGreaterThanOrEqual(0.6);
    expect(medMatching[0].data.confidence).toBeLessThan(0.85);

    const lowNodes = toFlowNodes(demoGraph.nodes, { query: '', kind: null, confidence: 'low' });
    const lowMatching = lowNodes.filter((n) => n.data.searchMatch);
    expect(lowMatching).toHaveLength(0);
  });

  it('detects active filter', () => {
    expect(hasActiveFilter(undefined)).toBe(false);
    expect(hasActiveFilter({ query: '', kind: null, confidence: null })).toBe(false);
    expect(hasActiveFilter({ query: 'test', kind: null, confidence: null })).toBe(true);
    expect(hasActiveFilter({ query: '', kind: 'valve', confidence: null })).toBe(true);
    expect(hasActiveFilter({ query: '', kind: null, confidence: 'high' })).toBe(true);
  });

  it('includes page number in node data', () => {
    const flowNodes = toFlowNodes(demoGraph.nodes);
    expect(flowNodes[0].data.page).toBe(0);
  });
});
