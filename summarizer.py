"""Some useful summarizers.

Summarizers condense (summarize) past input."""

# Copyright 2011 Matt Shannon

# This file is part of armspeech.
# See `License` for details of license and warranty.


from __future__ import division

from dist import *

class ContextualVectorSummarizer(object):
    def __init__(self, vectorSummarizer):
        self.vectorSummarizer = vectorSummarizer

    def __repr__(self):
        return 'ContextualVectorSummarizer('+repr(self.vectorSummarizer)+')'

    def __call__(self, input, partialOutput, outIndex):
        context, vectorInput = input
        summary = self.vectorSummarizer(vectorInput, partialOutput, outIndex)
        return context, summary

class VectorSeqSummarizer(object):
    def __init__(self, order, depths):
        self.order = order
        self.depths = depths

    def __repr__(self):
        return 'VectorSeqSummarizer('+repr(self.order)+', '+repr(self.depths)+')'

    def __call__(self, input, partialOutput, outIndex):
        depth = self.depths[outIndex]
        summary = map(lambda v: v[outIndex], input[-depth:] if depth > 0 else [])
        if len(summary) != depth:
            raise RuntimeError('input to summarize has incorrect depth (should be '+repr(depth)+' not '+repr(len(summary))+'): '+repr(input))
        return summary

    def createDist(self, contextual, createDistForIndex):
        vectorSummarizer = ContextualVectorSummarizer(self) if contextual else self
        return createVectorDist(self.order, sorted(self.depths.keys()), vectorSummarizer, createDistForIndex)

    def createAcc(self, contextual, createAccForIndex):
        vectorSummarizer = ContextualVectorSummarizer(self) if contextual else self
        return createVectorAcc(self.order, sorted(self.depths.keys()), vectorSummarizer, createAccForIndex)

class IndexSpecSummarizer(object):
    def __init__(self, outIndices, fromOffset, toOffset, order, depth, powers = [1]):
        self.outIndices = outIndices
        self.fromOffset = fromOffset
        self.toOffset = toOffset
        self.order = order
        self.depth = depth
        self.powers = powers

        self.limits = dict()
        for outIndex in outIndices:
            inFromIndex = min(max(outIndex + fromOffset, 0), order)
            inUntilIndex = min(max(outIndex + toOffset + 1, 0), order)
            self.limits[outIndex] = inFromIndex, inUntilIndex

    def __repr__(self):
        return 'IndexSpecSummarizer('+repr(self.outIndices)+', '+repr(self.fromOffset)+', '+repr(self.toOffset)+', '+repr(self.order)+', '+repr(self.depth)+', '+repr(self.powers)+')'

    def __call__(self, input, partialOutput, outIndex):
        if not outIndex in self.limits or len(input) != self.depth:
            raise RuntimeError('invalid input to summarize: '+repr(input))
        inFromIndex, inUntilIndex = self.limits[outIndex]
        summary = []
        for pastVec in input:
            for index in range(inFromIndex, inUntilIndex):
                for power in self.powers:
                    summary.append(pastVec[index] ** power)
        for index in range(inFromIndex, min(outIndex, inUntilIndex)):
            for power in self.powers:
                summary.append(partialOutput[index] ** power)
        return array(summary)

    def vectorLength(self, outIndex):
        inFromIndex, inUntilIndex = self.limits[outIndex]
        summaryLength = max(inUntilIndex - inFromIndex, 0) * len(self.powers) * self.depth + max(min(outIndex, inUntilIndex) - inFromIndex, 0) * len(self.powers)
        return summaryLength

    def createDist(self, contextual, createDistForIndex):
        vectorSummarizer = ContextualVectorSummarizer(self) if contextual else self
        return createVectorDist(self.order, self.outIndices, vectorSummarizer, createDistForIndex)

    def createAcc(self, contextual, createAccForIndex):
        vectorSummarizer = ContextualVectorSummarizer(self) if contextual else self
        return createVectorAcc(self.order, self.outIndices, vectorSummarizer, createAccForIndex)