"""Basic definitions for specifying distributed computations."""

# Copyright 2011, 2012 Matt Shannon

# This file is part of armspeech.
# See `License` for details of license and warranty.


from __future__ import division

from armspeech.util import persist

import os
import sys
import inspect
import modulefinder

def findDeps(srcFile):
    """Returns local dependencies for a given source file.

    Local means defined under PYTHONPATH (or in the same directory as the given
    source file if PYTHONPATH not defined), the idea being that local files are
    the ones subject to change and need to be hashed.
    It is assumed that modules that are on the system search path are fixed.
    """
    envPythonPath = os.environ['PYTHONPATH'] if 'PYTHONPATH' in os.environ else sys.path[0]
    finder = modulefinder.ModuleFinder(path = envPythonPath)
    finder.run_script(srcFile)
    depFiles = [ mod.__file__ for modName, mod in finder.modules.items() if mod.__file__ is not None ]
    return sorted(depFiles)

class Artifact(object):
    def secHash(self):
        secHashAllExternals = [ secHash for art in ancestorArtifacts([self]) for secHash in art.secHashExternals() ]
        return persist.secHashObject((self, secHashAllExternals, self.secHashSources()))

class FixedArtifact(Artifact):
    def __init__(self, location):
        self.location = location
    def parentJobs(self):
        return []
    def parentArtifacts(self):
        return []
    def secHashExternals(self):
        return [persist.secHashFile(self.location)]
    def secHashSources(self):
        return []
    def loc(self, baseDir):
        return self.location

class JobArtifact(Artifact):
    def __init__(self, parentJob):
        self.parentJob = parentJob
    def parentJobs(self):
        return [self.parentJob]
    def parentArtifacts(self):
        return self.parentJob.inputs
    def secHashExternals(self):
        return []
    def secHashSources(self):
        return [ persist.secHashFile(depFile) for depFile in findDeps(inspect.getsourcefile(self.parentJob.__class__)) ]
    def loc(self, baseDir):
        return os.path.join(baseDir, self.secHash())

def ancestorArtifacts(initialArts):
    ret = []
    agenda = list(initialArts)
    lookup = dict()
    while agenda:
        art = agenda.pop()
        ident = id(art)
        if not ident in lookup:
            lookup[ident] = True
            ret.append(art)
            agenda.extend(reversed(art.parentArtifacts()))
    return ret

class Job(object):
    # (N.B. some client code uses default hash routines)
    def parentJobs(self):
        return [ parentJob for input in self.inputs for parentJob in input.parentJobs() ]
    def newOutput(self):
        return JobArtifact(parentJob = self)
    def run(self, buildRepo):
        abstract
    def secHash(self):
        secHashAllExternals = [ secHash for art in ancestorArtifacts(self.inputs) for secHash in art.secHashExternals() ]
        return persist.secHashObject((self, secHashAllExternals))
