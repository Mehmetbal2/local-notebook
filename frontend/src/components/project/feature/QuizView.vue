<template>
  <div class="quiz">
    <div class="quiz-summary">
      <div class="quiz-score">
        <strong>{{ $t('ui.quizScore', { correct: correctCount, total: gradedTotal }) }}</strong>
        <span>{{ $t('ui.quizAnswered', { answered: answeredCount, total: questions.length }) }}</span>
      </div>
      <button class="btn btn-text" type="button" :disabled="answeredCount === 0" @click="reset">
        {{ $t('ui.quizReset') }}
      </button>
    </div>
    <div class="quiz-track" aria-hidden="true">
      <div class="quiz-track-fill" :style="{ width: `${(answeredCount / questions.length) * 100}%` }"></div>
    </div>

    <template v-for="(question, qi) in questions" :key="qi">
      <h3 v-if="question.group && question.group !== questions[qi - 1]?.group" class="quiz-group" dir="auto">
        {{ question.group }}
      </h3>

      <section class="question" :class="questionState(qi)">
        <div class="question-head" dir="auto">
          <span class="question-number">{{ qi + 1 }}</span>
          <p class="question-prompt">
            <BlockParts :parts="question.prompt" :active-citation-num="activeCitationNum" @citation-click="emit('citationClick', $event)" />
          </p>
        </div>

        <div v-if="question.options.length > 0" class="options" role="radiogroup">
          <button
            v-for="option in question.options"
            :key="option.letter"
            class="option"
            :class="optionState(qi, option.letter)"
            type="button"
            role="radio"
            :aria-checked="answers[qi] === option.letter"
            :disabled="answers[qi] !== undefined"
            dir="auto"
            @click="choose(qi, option.letter)"
          >
            <span class="option-letter">{{ option.letter }}</span>
            <span class="option-text">
              <BlockParts :parts="option.parts" :active-citation-num="activeCitationNum" @citation-click="emit('citationClick', $event)" />
            </span>
          </button>
        </div>

        <button v-else class="btn btn-outline reveal-btn" type="button" @click="toggleReveal(qi)">
          {{ answers[qi] !== undefined ? $t('ui.hideAnswer') : $t('ui.showAnswer') }}
        </button>

        <div v-if="answers[qi] !== undefined" class="explanation" dir="auto">
          <strong v-if="question.correct">
            {{ answers[qi] === question.correct ? $t('ui.correctAnswer') : $t('ui.wrongAnswer') }}
            · {{ question.correct }}
          </strong>
          <strong v-else>{{ $t('ui.modelAnswer') }}</strong>
          <p>
            <BlockParts :parts="question.explanation" :active-citation-num="activeCitationNum" @citation-click="emit('citationClick', $event)" />
          </p>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { FeatureCitationRefPart } from '../../../types'
import type { QuizQuestion } from './featureStructure'
import BlockParts from './BlockParts.vue'

const props = defineProps<{
  questions: QuizQuestion[]
  activeCitationNum?: number | null
}>()

const emit = defineEmits<{
  (e: 'citationClick', part: FeatureCitationRefPart): void
}>()

/** Chosen letter per question; 'shown' for a revealed short answer. */
const answers = ref<Record<number, string>>({})

const gradedTotal = computed(() => props.questions.filter((question) => question.correct).length)
const answeredCount = computed(() => Object.keys(answers.value).length)
const correctCount = computed(
  () => props.questions.filter((question, index) => question.correct && answers.value[index] === question.correct).length,
)

function choose(index: number, letter: string) {
  if (answers.value[index] !== undefined) return
  answers.value = { ...answers.value, [index]: letter }
}

function toggleReveal(index: number) {
  const next = { ...answers.value }
  if (next[index] !== undefined) delete next[index]
  else next[index] = 'shown'
  answers.value = next
}

function reset() {
  answers.value = {}
}

function questionState(index: number) {
  const question = props.questions[index]!
  const answer = answers.value[index]
  if (answer === undefined || !question.correct) return ''
  return answer === question.correct ? 'is-correct' : 'is-wrong'
}

function optionState(index: number, letter: string) {
  const question = props.questions[index]!
  const answer = answers.value[index]
  if (answer === undefined) return ''
  if (letter === question.correct) return 'correct'
  if (letter === answer) return 'wrong'
  return 'dimmed'
}

watch(() => props.questions, reset)
</script>

<style scoped>
.quiz {
  display: flex;
  flex-direction: column;
  gap: 14px;
  max-width: 720px;
  margin: 0 auto;
}

.quiz-summary {
  position: sticky;
  top: -1px;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 0 4px;
  background: var(--bg-white);
}

.quiz-score {
  display: flex;
  flex-direction: column;
  font-size: 12px;
  color: var(--text-tertiary);
}

.quiz-score strong {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.quiz-track {
  height: 4px;
  border-radius: 2px;
  background: var(--bg-tertiary);
  overflow: hidden;
}

.quiz-track-fill {
  height: 100%;
  background: var(--primary-color);
  border-radius: 2px;
  transition: width var(--duration-slow) var(--ease-emphasized);
}

.quiz-group {
  margin-top: 10px;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--text-tertiary);
}

.question {
  padding: 18px;
  border-radius: var(--radius-lg);
  background: var(--bg-secondary);
  box-shadow: inset 0 0 0 1px transparent;
  transition: box-shadow var(--duration-base);
}

.question.is-correct {
  box-shadow: inset 0 0 0 1px var(--success-color);
}

.question.is-wrong {
  box-shadow: inset 0 0 0 1px var(--error-color);
}

.question-head {
  display: flex;
  gap: 12px;
}

.question-number {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: var(--bg-white);
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}

.question-prompt {
  font-size: 15px;
  font-weight: 500;
  line-height: 1.5;
  color: var(--text-primary);
}

.options {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 14px;
}

.option {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  width: 100%;
  padding: 10px 14px;
  border-radius: var(--radius-md);
  background: var(--bg-white);
  box-shadow: inset 0 0 0 1px var(--border-color);
  color: var(--text-primary);
  font-size: 14px;
  line-height: 1.5;
  text-align: start;
}

.option:disabled {
  opacity: 1;
  cursor: default;
}

.option:hover:not(:disabled) {
  box-shadow: inset 0 0 0 1px var(--primary-color);
  background: var(--info-soft);
}

.option-letter {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--bg-tertiary);
  font-size: 12px;
  font-weight: 600;
}

.option.correct {
  background: var(--success-soft);
  box-shadow: inset 0 0 0 1px var(--success-color);
}

.option.correct .option-letter {
  background: var(--success-color);
  color: #fff;
}

.option.wrong {
  background: var(--error-soft);
  box-shadow: inset 0 0 0 1px var(--error-color);
}

.option.wrong .option-letter {
  background: var(--error-color);
  color: #fff;
}

.option.dimmed {
  opacity: 0.55;
}

.reveal-btn {
  margin-top: 14px;
  height: 36px;
}

.explanation {
  margin-top: 14px;
  padding: 12px 14px;
  border-radius: var(--radius-md);
  background: var(--bg-white);
  font-size: 14px;
  line-height: 1.6;
}

.explanation strong {
  display: block;
  margin-bottom: 4px;
  font-size: 12px;
  letter-spacing: 0.02em;
  color: var(--text-tertiary);
}

.is-correct .explanation strong {
  color: var(--success-color);
}

.is-wrong .explanation strong {
  color: var(--error-color);
}
</style>
