"""
مقاييس جودة الترجمة:
- BLEU, chrF, METEOR (مرجعية)
- COMET, BERTScore (بدون مرجع أو مرجعية)
- GLEU (جودة عامة)
"""
import logging
from dataclasses import dataclass, asdict
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class QualityScore:
    bleu: Optional[float] = None
    chrf: Optional[float] = None
    meteor: Optional[float] = None
    comet: Optional[float] = None
    bertscore: Optional[float] = None
    gleu: Optional[float] = None
    overall: Optional[float] = None
    level: str = "unknown"   # excellent|good|fair|poor


class QualityEvaluator:
    def __init__(self, use_comet: bool = False, use_bertscore: bool = False):
        self._bleu = None
        self._chrf = None
        self._meteor = None
        self._comet = None
        self._bertscore = None

        self.use_comet = use_comet
        self.use_bertscore = use_bertscore

    def _lazy_load(self):
        from evaluate import load

        if self._bleu is None:
            self._bleu = load("bleu")
        if self._chrf is None:
            self._chrf = load("chrf")
        if self._meteor is None:
            self._meteor = load("meteor")
        if self.use_comet and self._comet is None:
            try:
                self._comet = load("comet")
            except Exception as e:
                logger.warning("COMET غير متاح: %s", e)
        if self.use_bertscore and self._bertscore is None:
            try:
                self._bertscore = load("bertscore")
            except Exception as e:
                logger.warning("BERTScore غير متاح: %s", e)

    def evaluate(
        self,
        predictions: List[str],
        references: List[str],
        sources: Optional[List[str]] = None,
    ) -> QualityScore:
        self._lazy_load()

        score = QualityScore()

        try:
            score.bleu = self._bleu.compute(
                predictions=predictions,
                references=[[r] for r in references],
            )["bleu"] * 100
        except Exception as e:
            logger.warning("BLEU فشل: %s", e)

        try:
            score.chrf = self._chrf.compute(
                predictions=predictions,
                references=references,
            )["score"]
        except Exception as e:
            logger.warning("chrF فشل: %s", e)

        try:
            score.meteor = self._meteor.compute(
                predictions=predictions,
                references=references,
            )["meteor"] * 100
        except Exception as e:
            logger.warning("METEOR فشل: %s", e)

        if self.use_comet and self._comet and sources:
            try:
                score.comet = self._comet.compute(
                    predictions=predictions,
                    references=references,
                    sources=sources,
                )["mean_score"] * 100
            except Exception as e:
                logger.warning("COMET فشل: %s", e)

        if self.use_bertscore and self._bertscore:
            try:
                r = self._bertscore.compute(
                    predictions=predictions,
                    references=references,
                    lang="ar",
                )
                score.bertscore = sum(r["f1"]) / len(r["f1"]) * 100
            except Exception as e:
                logger.warning("BERTScore فشل: %s", e)

        # Overall = متوسط مرجّح
        weights = {"bleu": 0.25, "chrf": 0.25, "meteor": 0.25,
                   "comet": 0.25, "bertscore": 0.25}
        parts, wsum = 0, 0
        for k, w in weights.items():
            v = getattr(score, k)
            if v is not None:
                parts += v * w
                wsum += w
        if wsum:
            score.overall = parts / wsum

        # تصنيف
        if score.overall is not None:
            if score.overall >= 70:
                score.level = "excellent"
            elif score.overall >= 50:
                score.level = "good"
            elif score.overall >= 30:
                score.level = "fair"
            else:
                score.level = "poor"

        return score

    def to_dict(self, score: QualityScore) -> dict:
        return asdict(score)
