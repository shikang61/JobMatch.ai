import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "react-query";
import { getSession, evaluateAnswer, completeSession } from "../services/api";
import type {
  PrepQuestion,
  EvaluateAnswerResponse,
  CompleteSessionResponse,
} from "../services/api";
import { useState, useEffect, useRef, useCallback } from "react";

// ---------------------------------------------------------------------------
// Browser Speech API helpers
// ---------------------------------------------------------------------------

function speak(text: string, onEnd?: () => void) {
  if (!("speechSynthesis" in window)) {
    onEnd?.();
    return;
  }
  window.speechSynthesis.cancel();
  const utt = new SpeechSynthesisUtterance(text);
  utt.rate = 0.95;
  utt.pitch = 1;
  if (onEnd) utt.onend = onEnd;
  window.speechSynthesis.speak(utt);
}

// ---------------------------------------------------------------------------
// Chat message types
// ---------------------------------------------------------------------------

interface ChatMessage {
  role: "interviewer" | "candidate" | "system";
  text: string;
  score?: number;
  feedback?: EvaluateAnswerResponse;
}

// ---------------------------------------------------------------------------
// InterviewPractice page
// ---------------------------------------------------------------------------

export default function InterviewPractice() {
  const { sessionId: sessionIdParam } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: session, isLoading: sessionLoading } = useQuery(
    ["session", sessionIdParam],
    () => getSession(sessionIdParam!),
    { enabled: !!sessionIdParam }
  );

  const sessionId = sessionIdParam ?? null;
  const questions = session?.questions ?? [];
  const jobTitle = session?.job_title ?? "";
  const companyName = session?.company_name ?? "";

  const [started, setStarted] = useState(false);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [userInput, setUserInput] = useState("");
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [answers, setAnswers] = useState<Record<string, unknown>[]>([]);
  const [finalResult, setFinalResult] = useState<CompleteSessionResponse | null>(null);
  const [isCompleting, setIsCompleting] = useState(false);
  const [isLeaving, setIsLeaving] = useState(false);

  const chatEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const recognitionRef = useRef<unknown>(null);
  const continuousListeningRef = useRef(false);
  const leaveSaveRef = useRef({
    sessionId: null as string | null,
    answers: [] as Record<string, unknown>[],
    jobTitle: "",
    companyName: "",
    started: false,
    completed: false,
  });

  const currentQ = questions[currentIdx] as PrepQuestion | undefined;

  // Keep ref updated for leave-save
  useEffect(() => {
    leaveSaveRef.current = {
      sessionId,
      answers,
      jobTitle,
      companyName,
      started,
      completed: !!finalResult,
    };
  }, [sessionId, answers, jobTitle, companyName, started, finalResult]);

  // On leave: auto-end session and save progress so it appears in Progress
  useEffect(() => {
    return () => {
      const r = leaveSaveRef.current;
      if (!r.started || r.completed || !r.sessionId) return;
      completeSession({
        session_id: r.sessionId,
        answers: r.answers,
        job_title: r.jobTitle,
        company_name: r.companyName,
      })
        .then(() => {
          queryClient.invalidateQueries({ queryKey: ["progressStats"] });
          queryClient.invalidateQueries({ queryKey: ["session", sessionIdParam] });
        })
        .catch(() => {});
    };
  }, [queryClient, sessionIdParam]);

  // Auto-scroll chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const askQuestion = useCallback(
    (idx: number) => {
      const q = questions[idx];
      if (!q) return;
      const msg: ChatMessage = {
        role: "interviewer",
        text: q.question,
      };
      setMessages((prev) => [
        ...prev,
        { role: "system", text: `Question ${idx + 1} of ${questions.length} — ${q.type} (${q.difficulty})` },
        msg,
      ]);
      if (voiceEnabled) {
        setIsSpeaking(true);
        speak(q.question, () => setIsSpeaking(false));
      }
      setTimeout(() => inputRef.current?.focus(), 300);
    },
    [questions, voiceEnabled]
  );

  const beginInterview = () => {
    setStarted(true);
    const greeting: ChatMessage = {
      role: "interviewer",
      text: `Welcome! I'll be your interviewer today for ${companyName || "this role"}. We have ${questions.length} questions. Take your time with each answer.\n\nLet's begin.`,
    };
    setMessages([greeting]);
    if (voiceEnabled) {
      setIsSpeaking(true);
      speak(greeting.text, () => {
        setIsSpeaking(false);
        askQuestion(0);
      });
    } else {
      setTimeout(() => askQuestion(0), 800);
    }
  };

  // Submit answer
  const handleSubmit = async () => {
    const answer = userInput.trim();
    if (!answer || !currentQ || !sessionId) return;

    setMessages((prev) => [...prev, { role: "candidate", text: answer }]);
    setUserInput("");
    setIsEvaluating(true);

    try {
      const evaluation = await evaluateAnswer({
        session_id: sessionId,
        question: currentQ.question,
        question_type: currentQ.type,
        answer,
        job_title: jobTitle,
        company_name: companyName,
      });

      const feedbackMsg: ChatMessage = {
        role: "interviewer",
        text: evaluation.feedback,
        score: evaluation.score,
        feedback: evaluation,
      };
      setMessages((prev) => [...prev, feedbackMsg]);
      setAnswers((prev) => [
        ...prev,
        { question: currentQ.question, answer, score: evaluation.score, feedback: evaluation.feedback },
      ]);

      if (voiceEnabled) {
        setIsSpeaking(true);
        speak(evaluation.feedback, () => {
          setIsSpeaking(false);
          moveToNext(currentIdx);
        });
      } else {
        setTimeout(() => moveToNext(currentIdx), 1500);
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "system", text: "Could not evaluate answer. Let's continue." },
      ]);
      setAnswers((prev) => [
        ...prev,
        { question: currentQ.question, answer, score: 0, feedback: "" },
      ]);
      moveToNext(currentIdx);
    } finally {
      setIsEvaluating(false);
    }
  };

  const moveToNext = useCallback(
    (idx: number) => {
      const next = idx + 1;
      if (next < questions.length) {
        setCurrentIdx(next);
        setTimeout(() => askQuestion(next), 1000);
      } else {
        setMessages((prev) => [
          ...prev,
          { role: "interviewer", text: "That concludes our interview. Let me prepare your performance review..." },
        ]);
        if (voiceEnabled) {
          speak("That concludes our interview. Let me prepare your performance review.");
        }
      }
    },
    [questions.length, askQuestion, voiceEnabled]
  );

  // Complete session (show full review on this page)
  const handleComplete = async () => {
    if (!sessionId) return;
    setIsCompleting(true);
    try {
      const result = await completeSession({
        session_id: sessionId,
        answers,
        job_title: jobTitle,
        company_name: companyName,
      });
      setFinalResult(result);
      queryClient.invalidateQueries({ queryKey: ["progressStats"] });
      queryClient.invalidateQueries({ queryKey: ["session", sessionIdParam] });
    } catch {
      setMessages((prev) => [...prev, { role: "system", text: "Could not generate final review." }]);
    } finally {
      setIsCompleting(false);
    }
  };

  // End session and save progress, then go to Progress (no full review on this page)
  const endSessionAndLeave = async () => {
    if (!sessionId) return;
    setIsLeaving(true);
    try {
      await completeSession({
        session_id: sessionId,
        answers,
        job_title: jobTitle,
        company_name: companyName,
      });
      queryClient.invalidateQueries({ queryKey: ["progressStats"] });
      queryClient.invalidateQueries({ queryKey: ["session", sessionIdParam] });
      navigate("/progress");
    } catch {
      setMessages((prev) => [...prev, { role: "system", text: "Could not save. Try again or finish the interview." }]);
    } finally {
      setIsLeaving(false);
    }
  };

  // Voice input (Web Speech API) — mic stays on until user turns it off
  const toggleListening = () => {
    const SpeechRecognition =
      (window as unknown as Record<string, unknown>).SpeechRecognition ||
      (window as unknown as Record<string, unknown>).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert("Speech recognition not supported in this browser. Try Chrome.");
      return;
    }
    if (isListening) {
      continuousListeningRef.current = false;
      (recognitionRef.current as { stop: () => void })?.stop();
      setIsListening(false);
      return;
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const recognition = new (SpeechRecognition as any)();
    recognition.lang = "en-US";
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    recognition.onresult = (event: any) => {
      const transcript: string = event.results?.[event.results.length - 1]?.[0]?.transcript || "";
      if (transcript.trim()) {
        setUserInput((prev) => (prev ? prev + " " + transcript : transcript));
      }
    };
    recognition.onend = () => {
      if (continuousListeningRef.current && recognitionRef.current === recognition) {
        try {
          recognition.start();
        } catch {
          setIsListening(false);
        }
      } else {
        setIsListening(false);
      }
    };
    recognition.onerror = () => {
      setIsListening(false);
    };
    recognitionRef.current = recognition;
    continuousListeningRef.current = true;
    recognition.start();
    setIsListening(true);
  };

  const isInterviewDone = currentIdx >= questions.length - 1 && answers.length >= questions.length;

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  if (!sessionIdParam) return <p className="text-slate-500">No session selected.</p>;
  if (sessionLoading) return <p className="text-slate-500">Loading session…</p>;
  if (!session) return <p className="text-slate-500">Session not found.</p>;

  // Saved completed practice: show summary and link to start a new one
  if (session.status === "completed") {
    return (
      <div className="mx-auto max-w-2xl space-y-6">
        <h1 className="text-2xl font-bold text-slate-800">Practice completed</h1>
        <div className="rounded-xl border border-slate-200 bg-white p-6 space-y-4">
          <p className="text-slate-700">
            This practice for <strong>{companyName || "this company"}</strong>
            {jobTitle ? ` (${jobTitle})` : ""} was completed.
          </p>
          {session.performance_score != null && (
            <p className="text-lg">
              Score: <strong>{session.performance_score}/100</strong>
            </p>
          )}
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="rounded-lg bg-brand-600 px-5 py-2 text-sm font-medium text-white hover:bg-brand-700"
          >
            Back to prep
          </button>
        </div>
      </div>
    );
  }

  // Final results screen
  if (finalResult) {
    return (
      <div className="mx-auto max-w-2xl space-y-6">
        <h1 className="text-2xl font-bold text-slate-800">Interview Performance Review</h1>

        <div className="flex items-center gap-4 rounded-xl border border-slate-200 bg-white p-6">
          <div
            className={`flex h-20 w-20 items-center justify-center rounded-full text-2xl font-bold text-white ${
              finalResult.overall_score >= 70
                ? "bg-green-500"
                : finalResult.overall_score >= 50
                ? "bg-amber-500"
                : "bg-red-500"
            }`}
          >
            {finalResult.overall_score}
          </div>
          <div>
            <p className="text-lg font-semibold text-slate-800">Overall Score</p>
            <p className="text-slate-600">{finalResult.summary}</p>
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-xl border border-green-200 bg-green-50 p-5">
            <h3 className="mb-2 font-semibold text-green-800">Strengths</h3>
            <ul className="space-y-1 text-sm text-green-700">
              {finalResult.strengths.map((s: string, i: number) => (
                <li key={i} className="flex gap-2">
                  <span className="shrink-0">&#10003;</span> {s}
                </li>
              ))}
            </ul>
          </div>
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-5">
            <h3 className="mb-2 font-semibold text-amber-800">Areas to improve</h3>
            <ul className="space-y-1 text-sm text-amber-700">
              {finalResult.areas_to_improve.map((s: string, i: number) => (
                <li key={i} className="flex gap-2">
                  <span className="shrink-0">&#9679;</span> {s}
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="rounded-xl border border-brand-200 bg-brand-50 p-5">
          <h3 className="mb-1 font-semibold text-brand-800">Recommendation</h3>
          <p className="text-brand-700">{finalResult.recommendation}</p>
        </div>

        <div className="flex gap-3">
          <button
            type="button"
            onClick={() => navigate("/")}
            className="rounded-lg bg-brand-600 px-5 py-2 text-sm font-medium text-white hover:bg-brand-700"
          >
            Back to dashboard
          </button>
          <button
            type="button"
            onClick={() => navigate("/progress")}
            className="rounded-lg border border-slate-300 px-5 py-2 text-sm text-slate-700 hover:bg-slate-50"
          >
            View progress
          </button>
        </div>
      </div>
    );
  }

  // Pre-start screen (session loaded, in_progress)
  if (!started) {
    return (
      <div className="mx-auto max-w-2xl space-y-6">
        <h1 className="text-2xl font-bold text-slate-800">Interview Practice</h1>
        <div className="rounded-xl border border-slate-200 bg-white p-6 space-y-4">
          {companyName && (
            <p className="text-slate-600">
              Practicing for <strong>{companyName}</strong>
              {jobTitle ? ` — ${jobTitle}` : ""}
            </p>
          )}
          <p className="text-slate-700">
            You're about to do a mock interview with <strong>{questions.length} questions</strong>.
          </p>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={voiceEnabled}
                onChange={(e) => setVoiceEnabled(e.target.checked)}
                className="rounded border-slate-300 text-brand-600"
              />
              Enable voice (interviewer speaks questions aloud)
            </label>
          </div>
          <button
            type="button"
            onClick={beginInterview}
            className="rounded-lg bg-brand-600 px-6 py-2.5 font-medium text-white hover:bg-brand-700"
          >
            Begin interview
          </button>
        </div>
      </div>
    );
  }

  // Interview chat interface
  return (
    <div className="mx-auto flex max-w-2xl flex-col" style={{ height: "calc(100vh - 8rem)" }}>
      {/* Header */}
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-bold text-slate-800">Interview Practice</h1>
        <div className="flex items-center gap-3 text-sm text-slate-500">
          <span>
            {Math.min(currentIdx + 1, questions.length)}/{questions.length}
          </span>
          <div className="h-2 w-24 overflow-hidden rounded-full bg-slate-200">
            <div
              className="h-full rounded-full bg-brand-500 transition-all"
              style={{ width: `${(Math.min(answers.length, questions.length) / questions.length) * 100}%` }}
            />
          </div>
          <button
            type="button"
            onClick={() => setVoiceEnabled(!voiceEnabled)}
            className={`rounded px-2 py-0.5 text-xs ${voiceEnabled ? "bg-brand-100 text-brand-700" : "bg-slate-100 text-slate-500"}`}
            title={voiceEnabled ? "Voice on" : "Voice off"}
          >
            {voiceEnabled ? "Voice ON" : "Voice OFF"}
          </button>
          <button
            type="button"
            onClick={endSessionAndLeave}
            disabled={isLeaving || isCompleting}
            className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50 disabled:opacity-50"
            title="End session and save progress to Progress"
          >
            {isLeaving ? "Saving…" : "End & save"}
          </button>
        </div>
      </div>

      {/* Chat messages */}
      <div className="flex-1 overflow-y-auto rounded-xl border border-slate-200 bg-white p-4 space-y-3">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${
              msg.role === "candidate"
                ? "justify-end"
                : msg.role === "system"
                ? "justify-center"
                : "justify-start"
            }`}
          >
            {msg.role === "system" ? (
              <span className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-500">
                {msg.text}
              </span>
            ) : (
              <div
                className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                  msg.role === "candidate"
                    ? "bg-brand-600 text-white"
                    : "bg-slate-100 text-slate-800"
                }`}
              >
                <p className="whitespace-pre-wrap text-sm">{msg.text}</p>
                {msg.score != null && (
                  <div className="mt-2 flex items-center gap-2">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                        msg.score >= 7
                          ? "bg-green-100 text-green-700"
                          : msg.score >= 4
                          ? "bg-amber-100 text-amber-700"
                          : "bg-red-100 text-red-700"
                      }`}
                    >
                      {msg.score}/10
                    </span>
                  </div>
                )}
                {msg.feedback && (
                  <div className="mt-2 space-y-1 text-xs opacity-80">
                    {msg.feedback.strengths?.length > 0 && (
                      <p>+ {msg.feedback.strengths.join(", ")}</p>
                    )}
                    {msg.feedback.improvements?.length > 0 && (
                      <p>- {msg.feedback.improvements.join(", ")}</p>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
        {isEvaluating && (
          <div className="flex justify-start">
            <div className="rounded-2xl bg-slate-100 px-4 py-3">
              <span className="text-sm text-slate-500 animate-pulse">Evaluating your answer…</span>
            </div>
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      {/* Input area */}
      <div className="mt-3 space-y-2">
        {isInterviewDone && !finalResult ? (
          <button
            type="button"
            onClick={handleComplete}
            disabled={isCompleting}
            className="w-full rounded-lg bg-green-600 py-3 font-medium text-white hover:bg-green-700 disabled:opacity-50"
          >
            {isCompleting ? "Generating performance review…" : "Finish interview & get feedback"}
          </button>
        ) : (
          <div className="flex gap-2">
            <textarea
              ref={inputRef}
              value={userInput}
              onChange={(e) => setUserInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit();
                }
              }}
              placeholder={isSpeaking ? "Interviewer is speaking…" : "Type your answer (or use mic)… Press Enter to submit"}
              disabled={isEvaluating || isSpeaking}
              rows={2}
              className="flex-1 resize-none rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 disabled:opacity-50"
            />
            <div className="flex flex-col gap-1">
              <button
                type="button"
                onClick={toggleListening}
                disabled={isEvaluating || isSpeaking}
                className={`rounded-lg px-3 py-2 text-sm font-medium transition ${
                  isListening
                    ? "bg-red-500 text-white animate-pulse"
                    : "border border-slate-300 text-slate-700 hover:bg-slate-50"
                } disabled:opacity-50`}
                title={isListening ? "Stop listening" : "Start voice input"}
              >
                {isListening ? "Stop" : "Mic"}
              </button>
              <button
                type="button"
                onClick={handleSubmit}
                disabled={!userInput.trim() || isEvaluating || isSpeaking}
                className="rounded-lg bg-brand-600 px-3 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
              >
                Send
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
