"""Independent small-case oracle: no production feature/distance helpers."""
import copy
from fractions import Fraction
import itertools
import random
import unittest
from relay_timing_lab.clock.core import transform, aligned, legacy, ORIGIN
from relay_timing_lab.metrics import matching, delivery
from relay_timing_lab.model import Settings, simulate, observe
from relay_timing_lab.matcher import score_matrix


def oracle_hist(trace, width, end):
    return [sum(b for t,b in trace if k*width <= t < (k+1)*width and t <= end)
            for k in range(end//width+1)]


def oracle_distance(a,b):
    if not sum(a) or not sum(b): return Fraction(0 if sum(a)==sum(b) else 2)
    return sum(abs(Fraction(x,sum(a))-Fraction(y,sum(b))) for x,y in zip(a,b))


def oracle_transform(trace, off, drift):
    out=[]
    for t,b in trace:
        exact = Fraction(t-2000)*(1+Fraction(drift,1000000)) + 2000+off
        out.append([exact.numerator//exact.denominator,b])
    return out


class ClockOracleTests(unittest.TestCase):
    def test_300_seeded_transform_alignment_ties_and_accounting(self):
        for seed in range(300):
            rng=random.Random(seed)
            s=Settings(horizon_ms=800,drain_ms=200,capacity=1+seed%3,batch_ms=200,tick_ms=50)
            traces=[sorted([[rng.randrange(800),rng.choice([128,256,512])] for _ in range(rng.randrange(12))])
                    for _ in range(2+seed%2)]
            ingress=[[[t+2000,b] for t,b in tr] for tr in traces]
            for policy in ('immediate','batch','padded'):
                results=[simulate(tr,policy,s) for tr in traces]
                before=copy.deepcopy(results)
                costs=delivery(traces,results)
                off=rng.choice([-800,0,750,2400]);drift=rng.choice([-20000,-1,0,1,20000])
                egress=[transform([[t+2000,b] for t,b in observe(r)],off,drift) for r in results]
                for r, public in zip(results,egress):
                    self.assertEqual(public,oracle_transform([[t+2000,b] for t,b in observe(r)],off,drift))
                offsets=[-800,0,800];drifts=[-20000,0,20000]
                scores,winners,work=aligned(ingress,egress,200,5000,offsets,drifts,1000)
                self.assertEqual(work,len(traces)**2*9)
                for i,trace in enumerate(ingress):
                    for j,target in enumerate(egress):
                        candidates=[(oracle_distance(oracle_hist(oracle_transform(trace,o,d),200,5000),
                                                        oracle_hist(target,200,5000)),[o,d])
                                    for o in offsets for d in drifts]
                        best=min(v[0] for v in candidates)
                        self.assertEqual(scores[i][j],best)
                        self.assertEqual(winners[i][j],next(h for v,h in candidates if v==best))
                actual=matching(scores,list(range(len(traces))))
                for i,row in enumerate(scores):
                    # Enumerate random tie orders independently.
                    rankings=[]
                    for perm in itertools.permutations(range(len(row))):
                        ranked=sorted(perm,key=lambda j:row[j]);rankings.append(ranked.index(i)+1)
                    self.assertEqual(actual['per_flow'][i]['rank'],sum(rankings)/len(rankings))
                    self.assertAlmostEqual(actual['per_flow'][i]['top1'],rankings.count(1)/len(rankings))
                self.assertEqual(results,before)
                self.assertEqual(delivery(traces,results),costs)

    def test_collisions_and_exact_boundaries(self):
        self.assertEqual(transform([[2000,1],[2001,2]],0,-20000),[[2000,1],[2000,2]])
        for off in (-800,2400):
            for drift in (-20000,20000):
                tr=[[2000,1],[10000,2]]
                self.assertEqual(transform(tr,off,drift),oracle_transform(tr,off,drift))

    def test_legacy_guard_preserves_synchronized_scores(self):
        rng=random.Random(42)
        for _ in range(30):
            a=[sorted([[rng.randrange(6000),128] for _ in range(20)]) for _ in range(4)]
            b=[observe(simulate(x,'batch',Settings())) for x in a]
            shift=lambda flows:[[[t+2000,s] for t,s in tr] for tr in flows]
            lags=[0,100,200,400,800,1600]
            self.assertEqual(score_matrix(a,b,200,8000,lags),legacy(shift(a),shift(b),200,12000,lags))

    def test_limits_exhaustion_and_callback(self):
        with self.assertRaisesRegex(ValueError,'budget exhausted'):
            aligned([[],[]],[[],[]],200,12000,[-800,0,800],[0],11)
        with self.assertRaisesRegex(RuntimeError,'cancel'):
            aligned([[]],[[]],200,12000,[0],[0],1,lambda:(_ for _ in ()).throw(RuntimeError('cancel')))
        for bad in ([[[1,2,3]]],[[[-1,2]]],[[[3,1],[2,1]]],[[[12001,1]]]):
            with self.assertRaises(ValueError): legacy(bad,[[]],200,12000,[0])
        for off,drift in [(True,0),(2401,0),(0,20001)]:
            with self.assertRaises(ValueError): transform([],off,drift)

if __name__=='__main__':unittest.main()
