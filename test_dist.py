"""Unit tests for distributions, accumulators and model training."""

# Copyright 2011 Matt Shannon

# This file is part of armspeech.
# See `License` for details of license and warranty.


from __future__ import division

from dist import *
from model import *
from summarizer import VectorSeqSummarizer
from mathhelp import logSum
import phoneset_baby
import questions_baby
from iterhelp import chunkList

import test_transform

import unittest
import sys
from numpy import *
import random
from numpy.random import randn, randint
import numpy.linalg as la
from scipy import stats

def logProb_frames(dist, trainData):
    lp = 0.0
    frames = 0
    for input, output in trainData:
        lp += dist.logProb(input, output)
        frames += 1
    return lp, frames

def assert_allclose(actual, desired, rtol = 1e-7, atol = 1e-14, msg = 'items not almost equal'):
    if shape(actual) != shape(desired) or not allclose(actual, desired, rtol, atol):
        raise AssertionError(msg+'\n ACTUAL:  '+repr(actual)+'\n DESIRED: '+repr(desired))

def randTag():
    return 'tag'+str(randint(0, 1000000))

def simpleInputGen(dimIn, bias = False):
    while True:
        ret = randn(dimIn)
        if bias:
            ret[-1] = 1.0
        yield ret

# (FIXME : add tests to test full range of shapes for transform stuff)
# (FIXME : add tests for logProbDerivInput and logProbDerivOutput for dists where either input or output has a discrete component (applies to lots of below tests, e.g. logProbDerivOutput for IdentifiableMixtureDist))
# (FIXME : add tests for Transformed(Input|Output)Learn(Dist|Transform)AccEM (for the Transform ones, have to first add a transform that can be re-estimated using EM))
# (FIXME : deep test for Transformed(Input|Output)Dist doesn't seem to converge to close to true dist in terms of parameters.  Multiple local minima?  Or just very insensitive to details?  For more complicated transforms might the test procedure never converge?)

def gen_LinearGaussian(dimIn = 3, bias = False):
    coeff = randn(dimIn)
    variance = math.exp(randn())
    dist = LinearGaussian(coeff, variance).withTag(randTag())
    return dist, simpleInputGen(dimIn, bias = bias)

def gen_StudentDist(dimIn = 3):
    df = math.exp(randn() + 1.0)
    precision = math.exp(randn())
    dist = StudentDist(df, precision).withTag(randTag())
    return dist, simpleInputGen(dimIn)

def gen_ConstantClassifier(numClasses = 5):
    logProbs = randn(numClasses)
    logProbs -= logSum(logProbs)
    dist = ConstantClassifier(logProbs).withTag(randTag())
    return dist, simpleInputGen(0)

def gen_BinaryLogisticClassifier(dimIn = 3, bias = False, useZeroCoeff = False):
    if useZeroCoeff:
        w = zeros([dimIn])
    else:
        w = randn(dimIn)
    dist = BinaryLogisticClassifier(w).withTag(randTag())
    return dist, simpleInputGen(dimIn, bias = bias)

def gen_MixtureDist(dimIn):
    return gen_MixtureOfTwoExperts(dimIn = 3)

def gen_MixtureOfTwoExperts(dimIn = 3, bias = False):
    blc, blcGen = gen_BinaryLogisticClassifier(dimIn, bias = bias)
    dist0 = gen_LinearGaussian(dimIn)[0]
    dist1 = gen_LinearGaussian(dimIn)[0]
    dist = MixtureDist(blc, [dist0, dist1]).withTag(randTag())
    return dist, blcGen

def gen_IdentifiableMixtureDist(dimIn = 3, blcUseZeroCoeff = False):
    blc, blcGen = gen_BinaryLogisticClassifier(dimIn, useZeroCoeff = blcUseZeroCoeff)
    dist0 = FixedValueDist(None)
    dist1 = gen_LinearGaussian(dimIn)[0]
    dist = IdentifiableMixtureDist(blc, [dist0, dist1]).withTag(randTag())
    return dist, blcGen

def gen_VectorDist(order = 10, depth = 3):
    depths = dict([ (outIndex, depth) for outIndex in range(order) ])
    vectorSummarizer = VectorSeqSummarizer(order, depths)
    dist = vectorSummarizer.createDist(False, lambda outIndex:
        MappedInputDist(array,
            gen_LinearGaussian(depths[outIndex])[0]
        )
    ).withTag(randTag())
    def getInputGen():
        while True:
            yield randn(depth, order)
    return dist, getInputGen()

def gen_DiscreteDist(keys = ['a', 'b', 'c'], dimIn = 3):
    dist = createDiscreteDist(keys, lambda key:
        gen_LinearGaussian(dimIn)[0]
    ).withTag(randTag())
    def getInputGen():
        while True:
            yield random.choice(keys), randn(dimIn)
    return dist, getInputGen()

def gen_shared_DiscreteDist(keys = ['a', 'b', 'c'], dimIn = 3):
    subDist = gen_LinearGaussian(dimIn)[0]
    dist = createDiscreteDist(keys, lambda key:
        subDist
    ).withTag(randTag())
    def getInputGen():
        while True:
            yield random.choice(keys), randn(dimIn)
    return dist, getInputGen()

def gen_DecisionTree_with_LinearGaussian_leaves(splitProb = 0.49, dimIn = 3):
    phoneList = phoneset_baby.phoneList
    questionList = questions_baby.getQuestions()

    def decisionTree(phonesLeft):
        questionsLeft = []
        for question in questionList:
            yesSize = len(phonesLeft & question.phoneSubset)
            if 0 < yesSize < len(phonesLeft):
                questionsLeft.append(question)

        if random.random() > splitProb or not questionsLeft:
            return DecisionTreeLeaf(gen_LinearGaussian(dimIn)[0])
        else:
            question = random.choice(questionsLeft)
            return DecisionTreeNode(question, decisionTree(phonesLeft & question.phoneSubset), decisionTree(phonesLeft - question.phoneSubset))
    def getInputGen():
        while True:
            yield random.choice(phoneList), randn(dimIn)
    return decisionTree(frozenset(phoneList)).withTag(randTag()), getInputGen()

def gen_MappedInputDist(dimIn = 3, dimOut = 2):
    transform = test_transform.gen_genericTransform([dimIn], [dimOut])
    subDist = gen_LinearGaussian(dimOut)[0]
    return MappedInputDist(transform, subDist).withTag(randTag()), simpleInputGen(dimIn)

def gen_MappedOutputDist(dimInput = 3):
    outputTransform = test_transform.gen_genericOutputTransform([dimInput], [])
    subDist, inputGen = gen_LinearGaussian(dimInput)
    return MappedOutputDist(outputTransform, subDist).withTag(randTag()), inputGen

def gen_TransformedInputDist(dimIn = 3, dimOut = 2):
    transform = test_transform.gen_genericTransform([dimIn], [dimOut])
    subDist = gen_LinearGaussian(dimOut)[0]
    return TransformedInputDist(transform, subDist).withTag(randTag()), simpleInputGen(dimIn)

def gen_TransformedOutputDist(dimInput = 3):
    outputTransform = test_transform.gen_genericOutputTransform([dimInput], [])
    subDist, inputGen = gen_LinearGaussian(dimInput)
    return TransformedOutputDist(outputTransform, subDist).withTag(randTag()), inputGen

def gen_nestedTransformDist(dimInputs = [3, 4, 2]):
    assert len(dimInputs) >= 1
    dimIn = dimInputs[-1]
    dist = gen_LinearGaussian(dimIn)[0]
    if randint(0, 2) == 0:
        outputTransform = test_transform.gen_genericOutputTransform([dimIn], [])
        if randint(0, 2) == 0:
            dist = MappedOutputDist(outputTransform, dist)
        else:
            dist = TransformedOutputDist(outputTransform, dist)
    for dimIn, dimOut in reversed(zip(dimInputs, dimInputs[1:])):
        transform = test_transform.gen_genericTransform([dimIn], [dimOut])
        if randint(0, 2) == 0:
            dist = MappedInputDist(transform, dist)
        else:
            dist = TransformedInputDist(transform, dist)
        if randint(0, 2) == 0:
            outputTransform = test_transform.gen_genericOutputTransform([dimIn], [])
            if randint(0, 2) == 0:
                dist = MappedOutputDist(outputTransform, dist)
            else:
                dist = TransformedOutputDist(outputTransform, dist)
    return dist.withTag(randTag()), simpleInputGen(dimInputs[0])

def gen_PassThruDist(dimIn = 3):
    subDist, inputGen = gen_LinearGaussian(dimIn)
    return PassThruDist(subDist).withTag(randTag()), inputGen

def gen_DebugDist(maxOcc = None, dimIn = 3):
    subDist, inputGen = gen_LinearGaussian(dimIn)
    return DebugDist(maxOcc, subDist).withTag(randTag()), inputGen

def iidLogProb(dist, training):
    logProb = 0.0
    for input, output, occ in training:
        logProb += dist.logProb(input, output) * occ
    return logProb

def trainedAcc(dist, training):
    acc = defaultCreateAcc(dist)
    for input, output, occ in training:
        acc.add(input, output, occ)
    return acc

def trainedAccG(dist, training, ps = defaultParamSpec):
    acc = ps.createAccG(dist)
    for input, output, occ in training:
        acc.add(input, output, occ)
    return acc

def randomizeParams(dist, ps = defaultParamSpec):
    return ps.parseAll(dist, randn(*shape(ps.params(dist))))

def reparse(dist, ps):
    params = ps.params(dist)
    assert len(shape(params)) == 1
    distParsed = ps.parseAll(dist, params)
    paramsParsed = ps.params(distParsed)
    assert_allclose(paramsParsed, params)
    assert dist.tag == distParsed.tag
    return distParsed

def check_logProbDerivInput(dist, input, output, eps):
    inputDelta = randn(*shape(input)) * eps
    numericDelta = dist.logProb(input + inputDelta, output) - dist.logProb(input, output)
    analyticDelta = dot(inputDelta, dist.logProbDerivInput(input, output))
    assert_allclose(analyticDelta, numericDelta, rtol = 1e-4)

def check_logProbDerivOutput(dist, input, output, eps):
    outputDelta = randn(*shape(output)) * eps
    numericDelta = dist.logProb(input, output + outputDelta) - dist.logProb(input, output)
    analyticDelta = dot(outputDelta, dist.logProbDerivOutput(input, output))
    assert_allclose(analyticDelta, numericDelta, rtol = 1e-4)

def check_addAcc(dist, trainingAll, ps):
    accAll = trainedAccG(dist, trainingAll, ps = ps)
    logLikeAll = accAll.logLike()
    derivParamsAll = ps.derivParams(accAll)

    trainingParts = chunkList(trainingAll, numChunks = randint(1, 5))
    accs = [ trainedAccG(dist, trainingPart, ps = ps) for trainingPart in trainingParts ]
    accFull = accs[0]
    for acc in accs[1:]:
        addAcc(accFull, acc)
    logLikeFull = accFull.logLike()
    derivParamsFull = ps.derivParams(accFull)

    assert_allclose(logLikeFull, logLikeAll)
    assert_allclose(derivParamsFull, derivParamsAll)

def check_logLike(dist, training, iid, hasEM):
    assert iid == True
    logLikeFromDist = iidLogProb(dist, training)
    if hasEM:
        logLikeEM = trainedAcc(dist, training).logLike()
        assert_allclose(logLikeEM, logLikeFromDist)
    logLikeG = trainedAccG(dist, training).logLike()
    assert_allclose(logLikeG, logLikeFromDist)

def check_derivParams(dist, training, ps, eps):
    params = ps.params(dist)
    acc = trainedAccG(dist, training, ps = ps)
    logLike = acc.logLike()
    derivParams = ps.derivParams(acc)
    paramsDelta = randn(*shape(params)) * eps
    distNew = ps.parseAll(dist, params + paramsDelta)
    logLikeNew = trainedAccG(distNew, training, ps = ps).logLike()
    assert_allclose(ps.params(distNew), params + paramsDelta)

    numericDelta = logLikeNew - logLike
    analyticDelta = dot(derivParams, paramsDelta)
    assert_allclose(analyticDelta, numericDelta, rtol = 1e-4, atol = 1e-10)

def getTrainEM(initEstDist, verbosity = 0):
    def doTrainEM(training):
        def accumulate(acc):
            for input, output, occ in training:
                acc.add(input, output, occ)
        dist, logLike, occ = trainEM(initEstDist, accumulate, deltaThresh = 1e-9, verbosity = verbosity)
        assert initEstDist.tag != None
        assert dist.tag == initEstDist.tag
        return dist, logLike, occ
    return doTrainEM

def getTrainCG(initEstDist, ps = defaultParamSpec, verbosity = 0):
    def doTrainCG(training):
        def accumulate(acc):
            for input, output, occ in training:
                acc.add(input, output, occ)
        dist, logLike, occ = trainCG(initEstDist, accumulate, ps = ps, length = -500, verbosity = verbosity)
        assert initEstDist.tag != None
        assert dist.tag == initEstDist.tag
        return dist, logLike, occ
    return doTrainCG

def getTrainFromAcc(createAcc):
    def doTrainFromAcc(training):
        acc = createAcc()
        for input, output, occ in training:
            acc.add(input, output, occ)
        dist, logLike, occ = defaultEstimate(acc)
        assert acc.tag != None
        assert dist.tag == acc.tag
        return dist, logLike, occ
    return doTrainFromAcc

def check_est(trueDist, train, inputGen, hasParams, iid = True, unitOcc = False, ps = defaultParamSpec, logLikeThresh = 2e-2, tslpThresh = 2e-2, testSetSize = 50, initTrainingSetSize = 100, trainingSetMult = 5, maxTrainingSetSize = 100000):
    """Check estimation of distribution using expectation-maximization.

    (N.B. set train to getTrainEM(trueDist) instead of
    getTrainEM(<some random dist of the same form>) for a less stringent test
    (e.g. if there are local optima))
    """
    assert iid == True

    inputsTest = [ input for input, index in zip(inputGen, range(testSetSize)) ]
    testSet = [ (input, trueDist.synth(input), 1.0 if unitOcc else exp(randn())) for input in inputsTest ]
    testOcc = sum(occ for input, output, occ in testSet)

    training = []

    def extendTrainingSet(trainingSetSizeDelta):
        inputsNew = [ input for input, index in zip(inputGen, range(trainingSetSizeDelta)) ]
        trainingNew = [ (input, trueDist.synth(input), 1.0 if unitOcc else exp(randn())) for input in inputsNew ]
        training.extend(trainingNew)

    converged = False
    while not converged and len(training) < maxTrainingSetSize:
        extendTrainingSet((trainingSetMult - 1) * len(training) + initTrainingSetSize)
        trueLogProb = iidLogProb(trueDist, training)
        estDist, estLogLike, estOcc = train(training)
        # N.B. tests both that training has converged and that logLike from estimate agrees with iid logProb from dist
        # (FIXME : might be nice to separate these two criterion)
        assert_allclose(estLogLike, iidLogProb(estDist, training))
        assert_allclose(estOcc, sum(occ for input, output, occ in training))
        tslpTrue = iidLogProb(trueDist, testSet)
        tslpEst = iidLogProb(estDist, testSet)
        if hasParams:
            newAcc = trainedAccG(estDist, training, ps = ps)
            assert_allclose(newAcc.occ, estOcc)
            derivParams = ps.derivParams(newAcc)
            assert_allclose(derivParams / estOcc, zeros([len(derivParams)]), atol = 1e-4)
        if not isfinite(estLogLike):
            print 'NOTE: singularity in likelihood function (training set size =', len(training), ', occ '+repr(estOcc)+', estDist =', estDist, ', estLogLike =', estLogLike, ')'
        if abs(trueLogProb - estLogLike) / estOcc < logLikeThresh and abs(tslpTrue - tslpEst) / testOcc < tslpThresh:
            converged = True
    if not converged:
        raise AssertionError('estimated dist did not converge to true dist\n\ttraining set size = '+str(len(training))+'\n\ttrueLogProb = '+str(trueLogProb / estOcc)+' vs estLogLike = '+str(estLogLike / estOcc)+'\n\ttslpTrue = '+str(tslpTrue / testOcc)+' vs tslpEst = '+str(tslpEst / testOcc)+'\n\ttrueDist = '+repr(trueDist)+'\n\testDist = '+repr(estDist))

def getTrainingSet(dist, inputGen, typicalSize, iid, unitOcc):
    trainingSetSize = random.choice([0, 1, 2, typicalSize - 1, typicalSize, typicalSize + 1, 2 * typicalSize - 1, 2 * typicalSize, 2 * typicalSize + 1])
    inputs = [ input for input, index in zip(inputGen, range(trainingSetSize)) ]
    if iid:
        trainingSet = [ (input, dist.synth(input), 1.0 if unitOcc else exp(randn())) for input in inputs ]
    else:
        assert unitOcc == True
        # (FIXME : potentially very slow.  Could rewrite some of GP stuff to do this better if necessary.)
        updatedDist = dist
        trainingSet = []
        for inputNew in inputs:
            acc = defaultCreateAcc(updatedDist)
            for input, output, occ in trainingSet:
                acc.add(input, output, occ)
            updatedDist = defaultEstimate(acc)[0]
            trainingSet.append((inputNew, updatedDist.synth(inputNew), 1.0))
    assert len(trainingSet) == trainingSetSize
    return trainingSet

def checkLots(dist, inputGen, hasParams, eps, numPoints, iid = True, unitOcc = False, hasEM = True, ps = defaultParamSpec, logProbDerivInputCheck = False, logProbDerivOutputCheck = False, checkAdditional = None):
    # (FIXME : add pickle test)
    # (FIXME : add eval test)
    assert dist.tag != None
    if hasEM:
        assert defaultCreateAcc(dist).tag == dist.tag
    assert ps.createAccG(dist).tag == dist.tag

    training = getTrainingSet(dist, inputGen, typicalSize = numPoints, iid = iid, unitOcc = unitOcc)

    points = []
    for pointIndex in range(numPoints):
        input = inputGen.next()
        output = dist.synth(input)
        points.append((input, output))

    logProbsBefore = [ dist.logProb(input, output) for input, output in points ]
    if hasParams:
        paramsBefore = ps.params(dist)

    distMapped = nodetree.defaultMap(dist)
    assert id(distMapped) != id(dist)
    assert distMapped.tag == dist.tag
    if hasParams:
        distParsed = reparse(dist, ps)
    for input, output in points:
        if isfinite(dist.logProb(input, output)):
            if checkAdditional != None:
                checkAdditional(dist, input, output, eps)
            lp = dist.logProb(input, output)
            assert_allclose(distMapped.logProb(input, output), lp)
            if hasParams:
                assert_allclose(distParsed.logProb(input, output), lp)
            if logProbDerivInputCheck:
                check_logProbDerivInput(dist, input, output, eps)
            if logProbDerivOutputCheck:
                check_logProbDerivOutput(dist, input, output, eps)
        else:
            print 'NOTE: skipping point with logProb =', dist.logProb(input, output), 'for dist =', dist, 'input =', input, 'output =', output

    if hasParams:
        # (FIXME : add addAcc check for Accs which are not AccGs)
        check_addAcc(dist, training, ps)
    if iid:
        check_logLike(dist, training, iid = iid, hasEM = hasEM)
    if hasParams:
        check_derivParams(dist, training, ps, eps = eps)

    logProbsAfter = [ dist.logProb(input, output) for input, output in points ]
    assert_allclose(logProbsAfter, logProbsBefore, msg = 'looks like parsing affected the original distribution, which should never happen')
    if hasParams:
        paramsAfter = ps.params(dist)
        assert_allclose(logProbsAfter, logProbsBefore, rtol = 1e-10, msg = 'looks like parsing affected the original distribution, which should never happen')

# FIXME : make more configurable (e.g. from command line)
deepTest = False

class TestDist(unittest.TestCase):
    def test_Memo_random_subset(self, its = 10000):
        """Memo class random subsets should be equally likely to include each element"""
        for n in range(0, 5):
            for k in range(n + 1):
                count = zeros(n)
                for rep in xrange(its):
                    acc = Memo(maxOcc = k)
                    for i in xrange(n):
                        acc.add(i, i)
                    for i in acc.outputs:
                        count[i] += 1
                # (FIXME : thresh hardcoded for 'its' value (and small n, k).  Could compute instead.)
                self.assertTrue(la.norm(count / its * n - k) <= 0.05 * n, msg = 'histogram '+repr(count / its)+' for (n, k) = '+repr((n, k)))

    def test_LinearGaussian(self, eps = 1e-8, numDists = 50, numPoints = 100):
        for distIndex in range(numDists):
            bias = random.choice([True, False])
            dimIn = randint(1 if bias else 0, 5)
            dist, inputGen = gen_LinearGaussian(dimIn, bias = bias)
            checkLots(dist, inputGen, hasParams = True, eps = eps, numPoints = numPoints, logProbDerivInputCheck = True, logProbDerivOutputCheck = True)
            if deepTest:
                initEstDist = gen_LinearGaussian(dimIn)[0]
                check_est(dist, getTrainEM(initEstDist), inputGen, hasParams = True)
                check_est(dist, getTrainCG(initEstDist), inputGen, hasParams = True)
                createAcc = lambda: LinearGaussianAcc(inputLength = dimIn).withTag(randTag())
                check_est(dist, getTrainFromAcc(createAcc), inputGen, hasParams = True)

    def test_StudentDist(self, eps = 1e-8, numDists = 50, numPoints = 100):
        def checkAdditional(dist, input, output, eps):
            assert_allclose(dist.logProb(input, output), log(stats.t.pdf(output, dist.df, scale = 1.0 / sqrt(dist.precision))))
        for distIndex in range(numDists):
            dimIn = randint(0, 5)
            dist, inputGen = gen_StudentDist(dimIn)
            checkLots(dist, inputGen, hasParams = True, eps = eps, numPoints = numPoints, hasEM = False, logProbDerivInputCheck = True, logProbDerivOutputCheck = True, checkAdditional = checkAdditional)
            if deepTest:
                initEstDist = gen_StudentDist(dimIn)[0]
                check_est(dist, getTrainCG(initEstDist), inputGen, hasParams = True)

    def test_ConstantClassifier(self, eps = 1e-8, numDists = 50, numPoints = 100):
        for distIndex in range(numDists):
            numClasses = randint(1, 5)
            dist, inputGen = gen_ConstantClassifier(numClasses)
            checkLots(dist, inputGen, hasParams = True, eps = eps, numPoints = numPoints, logProbDerivInputCheck = True)
            if deepTest:
                initEstDist = gen_ConstantClassifier(numClasses)[0]
                check_est(dist, getTrainEM(initEstDist), inputGen, hasParams = True)
                check_est(dist, getTrainCG(initEstDist), inputGen, hasParams = True)
                createAcc = lambda: ConstantClassifierAcc(numClasses = numClasses).withTag(randTag())
                check_est(dist, getTrainFromAcc(createAcc), inputGen, hasParams = True)

    def test_BinaryLogisticClassifier(self, eps = 1e-8, numDists = 50, numPoints = 100):
        for distIndex in range(numDists):
            bias = random.choice([True, False])
            dimIn = randint(1 if bias else 0, 5)
            dist, inputGen = gen_BinaryLogisticClassifier(dimIn, bias = bias)
            checkLots(dist, inputGen, hasParams = True, eps = eps, numPoints = numPoints, logProbDerivInputCheck = True)
            if deepTest:
                # (useZeroCoeff since it seems to alleviate BinaryLogisticClassifier's convergence issues)
                initEstDist = gen_BinaryLogisticClassifier(dimIn, bias = bias, useZeroCoeff = True)[0]
                check_est(dist, getTrainEM(initEstDist), inputGen, hasParams = True)
                check_est(dist, getTrainCG(initEstDist), inputGen, hasParams = True)

    def test_estimateInitialMixtureOfTwoExperts(self, eps = 1e-8, numDists = 3):
        if deepTest:
            for distIndex in range(numDists):
                dimIn = randint(1, 5)
                dist, inputGen = gen_MixtureOfTwoExperts(dimIn, bias = True)
                def train(training):
                    def accumulate(acc):
                        for input, output, occ in training:
                            acc.add(input, output, occ)
                    acc = LinearGaussianAcc(inputLength = dimIn)
                    accumulate(acc)
                    initDist, initLogLike, initOcc = acc.estimateInitialMixtureOfTwoExperts()
                    return trainEM(initDist, accumulate, deltaThresh = 1e-9)
                check_est(dist, train, inputGen, hasParams = True)

    def test_MixtureDist(self, eps = 1e-8, numDists = 10, numPoints = 100):
        for distIndex in range(numDists):
            dimIn = randint(0, 5)
            dist, inputGen = gen_MixtureDist(dimIn)
            checkLots(dist, inputGen, hasParams = True, eps = eps, numPoints = numPoints, logProbDerivInputCheck = True, logProbDerivOutputCheck = True)
            if deepTest:
                check_est(dist, getTrainEM(dist), inputGen, hasParams = True)
                check_est(dist, getTrainCG(dist), inputGen, hasParams = True)

    def test_IdentifiableMixtureDist(self, eps = 1e-8, numDists = 20, numPoints = 100):
        for distIndex in range(numDists):
            dimIn = randint(0, 5)
            dist, inputGen = gen_IdentifiableMixtureDist(dimIn)
            checkLots(dist, inputGen, hasParams = True, eps = eps, numPoints = numPoints, logProbDerivInputCheck = True)
            if deepTest:
                initEstDist = gen_IdentifiableMixtureDist(dimIn, blcUseZeroCoeff = True)[0]
                check_est(dist, getTrainEM(initEstDist), inputGen, hasParams = True)
                check_est(dist, getTrainCG(initEstDist), inputGen, hasParams = True)

    def test_VectorDist(self, eps = 1e-8, numDists = 20, numPoints = 100):
        for distIndex in range(numDists):
            order = randint(0, 5)
            depth = randint(0, 5)
            dist, inputGen = gen_VectorDist(order, depth)
            checkLots(dist, inputGen, hasParams = True, eps = eps, numPoints = numPoints)
            if deepTest:
                initEstDist = gen_VectorDist(order, depth)[0]
                check_est(dist, getTrainEM(initEstDist), inputGen, hasParams = True)
                check_est(dist, getTrainCG(initEstDist), inputGen, hasParams = True)

    def test_DiscreteDist(self, eps = 1e-8, numDists = 20, numPoints = 100):
        for distIndex in range(numDists):
            keys = list('abcde')[:randint(1, 5)]
            dimIn = randint(0, 5)
            dist, inputGen = gen_DiscreteDist(keys, dimIn)
            checkLots(dist, inputGen, hasParams = True, eps = eps, numPoints = numPoints, logProbDerivOutputCheck = True)
            if deepTest:
                initEstDist = gen_DiscreteDist(keys, dimIn)[0]
                check_est(dist, getTrainEM(initEstDist), inputGen, hasParams = True)
                check_est(dist, getTrainCG(initEstDist), inputGen, hasParams = True)

    def test_DecisionTree(self, eps = 1e-8, numDists = 20, numPoints = 100):
        for distIndex in range(numDists):
            dimIn = randint(0, 5)
            dist, inputGen = gen_DecisionTree_with_LinearGaussian_leaves(splitProb = 0.49, dimIn = dimIn)
            checkLots(dist, inputGen, hasParams = True, eps = eps, numPoints = numPoints, logProbDerivOutputCheck = True)
            if deepTest:
                initEstDist = randomizeParams(dist)
                check_est(dist, getTrainEM(initEstDist), inputGen, hasParams = True)
                check_est(dist, getTrainCG(initEstDist), inputGen, hasParams = True)

    def test_decisionTreeCluster(self, eps = 1e-8, numDists = 20):
        if deepTest:
            for distIndex in range(numDists):
                dimIn = randint(0, 5)
                dist, inputGen = gen_DecisionTree_with_LinearGaussian_leaves(splitProb = 0.49, dimIn = dimIn)
                def train(training):
                    acc = AutoGrowingDiscreteAcc(createAcc = lambda: LinearGaussianAcc(inputLength = dimIn))
                    totalOcc = 0.0
                    for input, output, occ in training:
                        acc.add(input, output, occ)
                        totalOcc += occ
                    mdlThresh = 0.5 * (dimIn + 1) * log(totalOcc)
                    return acc.decisionTreeCluster(questions_baby.getQuestions(), thresh = mdlThresh, minOcc = 0.0, verbosity = 0)
                check_est(dist, train, inputGen, hasParams = True)

    def test_MappedInputDist(self, eps = 1e-8, numDists = 20, numPoints = 100):
        for distIndex in range(numDists):
            dimIn = randint(0, 5)
            if randint(0, 2) == 0:
                dimOut = dimIn
            else:
                dimOut = randint(0, 5)
            dist, inputGen = gen_MappedInputDist(dimIn, dimOut)
            checkLots(dist, inputGen, hasParams = True, eps = eps, numPoints = numPoints, logProbDerivInputCheck = True, logProbDerivOutputCheck = True)
            if deepTest:
                initEstDist = randomizeParams(dist)
                check_est(dist, getTrainEM(initEstDist), inputGen, hasParams = True)
                check_est(dist, getTrainCG(initEstDist), inputGen, hasParams = True)

    def test_MappedOutputDist(self, eps = 1e-8, numDists = 20, numPoints = 100):
        for distIndex in range(numDists):
            dimInput = randint(0, 5)
            dist, inputGen = gen_MappedOutputDist(dimInput)
            checkLots(dist, inputGen, hasParams = True, eps = eps, numPoints = numPoints, logProbDerivInputCheck = True, logProbDerivOutputCheck = True)
            if deepTest:
                initEstDist = randomizeParams(dist)
                check_est(dist, getTrainEM(initEstDist), inputGen, hasParams = True)
                check_est(dist, getTrainCG(initEstDist), inputGen, hasParams = True)

    def test_TransformedInputDist(self, eps = 1e-8, numDists = 10, numPoints = 100):
        for distIndex in range(numDists):
            dimIn = randint(0, 5)
            if randint(0, 2) == 0:
                dimOut = dimIn
            else:
                dimOut = randint(0, 5)
            dist, inputGen = gen_TransformedInputDist(dimIn, dimOut)
            checkLots(dist, inputGen, hasParams = True, eps = eps, numPoints = numPoints, logProbDerivInputCheck = True, logProbDerivOutputCheck = True)
            if deepTest:
                initEstDist = randomizeParams(dist)
                check_est(dist, getTrainCG(initEstDist), inputGen, hasParams = True)

    def test_TransformedOutputDist(self, eps = 1e-8, numDists = 10, numPoints = 100):
        for distIndex in range(numDists):
            dimInput = randint(0, 5)
            dist, inputGen = gen_TransformedOutputDist(dimInput)
            checkLots(dist, inputGen, hasParams = True, eps = eps, numPoints = numPoints, logProbDerivInputCheck = True, logProbDerivOutputCheck = True)
            if deepTest:
                initEstDist = randomizeParams(dist)
                check_est(dist, getTrainCG(initEstDist), inputGen, hasParams = True)

    def test_nestedTransformDist(self, eps = 1e-8, numDists = 10, numPoints = 100):
        for distIndex in range(numDists):
            numInputs = randint(1, 4)
            dimInputs = [ randint(0, 5) for i in range(numInputs) ]
            dist, inputGen = gen_nestedTransformDist(dimInputs)
            checkLots(dist, inputGen, hasParams = True, eps = eps, numPoints = numPoints, logProbDerivInputCheck = True, logProbDerivOutputCheck = True)
            if deepTest:
                initEstDist = randomizeParams(dist)
                check_est(dist, getTrainCG(initEstDist), inputGen, hasParams = True)

    def test_PassThruDist(self, eps = 1e-8, numDists = 20, numPoints = 100):
        for distIndex in range(numDists):
            dimIn = randint(0, 5)
            dist, inputGen = gen_PassThruDist(dimIn)
            checkLots(dist, inputGen, hasParams = True, eps = eps, numPoints = numPoints, logProbDerivInputCheck = True, logProbDerivOutputCheck = True)
            if deepTest:
                initEstDist = gen_PassThruDist(dimIn)[0]
                check_est(dist, getTrainEM(initEstDist), inputGen, hasParams = True)
                check_est(dist, getTrainCG(initEstDist), inputGen, hasParams = True)

    def test_DebugDist(self, eps = 1e-8, numDists = 20, numPoints = 100):
        for distIndex in range(numDists):
            maxOcc = random.choice([0, 1, 10, 100, None])
            dimIn = randint(0, 5)
            dist, inputGen = gen_DebugDist(maxOcc = maxOcc, dimIn = dimIn)
            checkLots(dist, inputGen, hasParams = True, eps = eps, numPoints = numPoints, iid = True, unitOcc = True, logProbDerivInputCheck = True, logProbDerivOutputCheck = True)
            if deepTest:
                initEstDist = gen_DebugDist(maxOcc = maxOcc, dimIn = dimIn)[0]
                check_est(dist, getTrainEM(initEstDist), inputGen, hasParams = True, iid = True, unitOcc = True)
                check_est(dist, getTrainCG(initEstDist), inputGen, hasParams = True, iid = True, unitOcc = True)

    # FIXME : fix code to make this test pass!
    def test_shared_DiscreteDist(self, eps = 1e-8, numDists = 20, numPoints = 100):
        for distIndex in range(numDists):
            keys = list('abcde')[:randint(1, 5)]
            dimIn = randint(0, 5)
            dist, inputGen = gen_shared_DiscreteDist(keys, dimIn)
            checkLots(dist, inputGen, hasParams = True, eps = eps, numPoints = numPoints, logProbDerivOutputCheck = True)
            if deepTest:
                initEstDist = gen_shared_DiscreteDist(keys, dimIn)[0]
                check_est(dist, getTrainEM(initEstDist), inputGen, hasParams = True)
                check_est(dist, getTrainCG(initEstDist), inputGen, hasParams = True)

    # FIXME : add more tests for shared dists

    # FIXME : add SequenceDist test

# FIXME : this is nowhere near a proper unit test (need to make it more robust, automated, etc)
def testBinaryLogisticClassifier():
    def inputGen(num):
        for i in range(num):
            yield append(randn(dim), 1.0)

    dim = 2
    blcTrue = BinaryLogisticClassifier(randn(dim + 1))
    num = 10000
    trainData = list((input, blcTrue.synth(input)) for input in inputGen(num))
    def accumulate(acc):
        for input, output in trainData:
            acc.add(input, output)

    blc = BinaryLogisticClassifier(zeros([dim + 1]))
    blc, trainLogLike, trainOcc = trainEM(blc, accumulate, deltaThresh = 1e-10, minIterations = 10, verbosity = 2)
    print 'training log likelihood =', trainLogLike / trainOcc, '('+str(trainOcc)+' frames)'
    trainLogProb, trainOcc = logProb_frames(blc, trainData)
    print 'train set log prob =', trainLogProb / trainOcc, '('+str(trainOcc)+' frames)'

    print
    print 'DEBUG: (training data set size is', len(trainData), 'of which:'
    print 'DEBUG:    count(0) =', len([ input for input, output in trainData if output == 0])
    print 'DEBUG:    count(1) =', len([ input for input, output in trainData if output == 1])
    print 'DEBUG: )'
    print
    print 'true coeff =', blcTrue.coeff
    print 'estimated coeff =', blc.coeff
    dist = la.norm(blcTrue.coeff - blc.coeff)
    print '(Euclidean distance =', dist, ')'

    if dist > 0.1:
        sys.stderr.write('WARNING: unusually large discrepancy between estimated and true dist during BinaryLogisticClassifier test\n')

# (N.B. not a unit test.  Just draws pictures to help you assess whether results seem reasonable.)
def testBinaryLogisticClassifierFunGraph():
    import pylab

    def location(blc):
        coeff = blc.coeff
        w = coeff[:-1]
        w0 = coeff[-1]
        mag = la.norm(w)
        normal = w / mag
        perpDist = -w0 / mag
        bdyPoint = normal * perpDist
        bdyPointProb = blc.prob(append(bdyPoint, 1.0), 0)
        if abs(bdyPointProb - 0.5) > 1e-10:
            raise RuntimeError('value at bdyPoint should be 0.5 but is '+str(bdyPointProb))
        return mag, normal, bdyPoint
    dim = 2
    wTrue = randn(dim + 1)
    blcTrue = BinaryLogisticClassifier(wTrue)
    print 'DEBUG: wTrue =', wTrue
    print
    def inputGen(num):
        for i in range(num):
            yield append(randn(dim), 1.0)

    num = 3000
    trainData = list((input, blcTrue.synth(input)) for input in inputGen(num))
    def accumulate(acc):
        for input, output in trainData:
            acc.add(input, output)
    print 'DEBUG: (in training data:'
    print 'DEBUG:    count(0) =', len([ input for input, output in trainData if output == 0])
    print 'DEBUG:    count(1) =', len([ input for input, output in trainData if output == 1])
    print 'DEBUG: )'

    def plotBdy(blc):
        mag, normal, bdyPoint = location(blc)
        dir = array([normal[1], -normal[0]])
        if abs(dot(dir, normal)) > 1e-10:
            raise RuntimeError('dir and normal are not perpendicular (should never happen)')
        xBdy, yBdy = zip(*[bdyPoint - 5 * dir, bdyPoint + 5 * dir])
        xBdy0, yBdy0 = zip(*[bdyPoint - normal / mag - 5 * dir, bdyPoint - normal / mag + 5 * dir])
        xBdy1, yBdy1 = zip(*[bdyPoint + normal / mag - 5 * dir, bdyPoint + normal / mag + 5 * dir])
        pylab.plot(xBdy, yBdy, 'k-', xBdy0, yBdy0, 'r-', xBdy1, yBdy1, 'b-')

    def plotData():
        x0, y0 = zip(*[ input[:-1] for input, output in trainData if output == 0 ])
        x1, y1 = zip(*[ input[:-1] for input, output in trainData if output == 1 ])
        pylab.plot(x0, y0, 'r+', x1, y1, 'bx')
        pylab.xlim(-3.5, 3.5)
        pylab.ylim(-3.5, 3.5)
        pylab.xlabel('x')
        pylab.ylabel('y')
        pylab.grid(True)

    def afterEst(dist, it):
        plotBdy(dist)

    plotData()
    plotBdy(blcTrue)

    blc = BinaryLogisticClassifier(zeros([dim + 1]))
    blc, trainLogLike, trainOcc = trainEM(blc, accumulate, deltaThresh = 1e-4, minIterations = 10, maxIterations = 50, afterEst = afterEst, verbosity = 2)
    print 'DEBUG: w estimated final =', blc.coeff
    print 'training log likelihood =', trainLogLike / trainOcc, '('+str(trainOcc)+' frames)'
    trainLogProb, trainOcc = logProb_frames(blc, trainData)
    print 'train set log prob =', trainLogProb / trainOcc, '('+str(trainOcc)+' frames)'

    pylab.show()

# (N.B. not a unit test.  Just draws pictures to help you assess whether results seem reasonable.)
def testMixtureOfTwoExpertsInitialization():
    import pylab

    def location(blc):
        coeff = blc.coeff
        w = coeff[:-1]
        w0 = coeff[-1]
        mag = la.norm(w)
        normal = w / mag
        perpDist = -w0 / mag
        bdyPoint = normal * perpDist
        bdyPointProb = blc.prob(append(bdyPoint, 1.0), 0)
        if abs(bdyPointProb - 0.5) > 1e-10:
            raise RuntimeError('value at bdyPoint should be 0.5 but is '+str(bdyPointProb))
        return mag, normal, bdyPoint
    dim = 2
    def inputGen(num):
        numClasses = 1
        transform = []
        bias = []
        for classIndex in range(numClasses):
            transform.append(randn(dim, dim) * 0.5)
            bias.append(randn(dim) * 3.0)
        for i in range(num):
            classIndex = randint(0, numClasses)
            yield append(dot(transform[classIndex], randn(dim)) + bias[classIndex], 1.0)

    num = 10000
    trainData = list((input, randn()) for input in inputGen(num))
    def accumulate(acc):
        for input, output in trainData:
            acc.add(input, output)

    def plotBdy(blc):
        mag, normal, bdyPoint = location(blc)
        dir = array([normal[1], -normal[0]])
        if abs(dot(dir, normal)) > 1e-10:
            raise RuntimeError('dir and normal are not perpendicular (should never happen)')
        xBdy, yBdy = zip(*[bdyPoint - 5 * dir, bdyPoint + 5 * dir])
        xBdy0, yBdy0 = zip(*[bdyPoint - normal / mag - 5 * dir, bdyPoint - normal / mag + 5 * dir])
        xBdy1, yBdy1 = zip(*[bdyPoint + normal / mag - 5 * dir, bdyPoint + normal / mag + 5 * dir])
        xDir, yDir = zip(*[bdyPoint - 5 * normal, bdyPoint + 5 * normal])
        pylab.plot(xBdy, yBdy, 'k-', xBdy0, yBdy0, 'r-', xBdy1, yBdy1, 'b-', xDir, yDir, 'g-')

    def plotData():
        x, y = zip(*[ input[:-1] for input, output in trainData ])
        pylab.plot(x, y, 'r+')
        pylab.xlabel('x')
        pylab.ylabel('y')
        pylab.grid(True)

    plotData()

    acc = LinearGaussianAcc(inputLength = dim + 1)
    accumulate(acc)
    dist, trainLogLike, trainOcc = acc.estimateInitialMixtureOfTwoExperts()
    blc = dist.classDist
    plotBdy(blc)
    print 'DEBUG: w estimated final =', blc.coeff

    pylab.xlim(-10.0, 10.0)
    pylab.ylim(-10.0, 10.0)
    pylab.show()

if __name__ == '__main__':
    unittest.main()
