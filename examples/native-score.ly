\version "2.26.0"

% Original, self-contained example. Edit the music directly and run LilyPond.
% These notes demonstrate syntax; they do not prescribe a composition style.

#(set-global-staff-size 18)

\header {
  title = "Flowing Lines"
  subtitle = "Piano study"
  tagline = ##f
}

\paper {
  paper-width = 210\mm
  paper-height = 148\mm
  top-margin = 10\mm
  bottom-margin = 10\mm
  left-margin = 12\mm
  right-margin = 12\mm
  ragged-last = ##f
  ragged-bottom = ##t
}

global = {
  \key c \major
  \time 4/4
}

rightHand = {
  \global
  \tempo "Andante" 4 = 76
  % Bar 1: three eighth notes in the space of two eighth notes.
  \tuplet 3/2 { e''8( g'' a'') } g''4 e'' d'' |
  % Bar 2: five sixteenth notes in the space of four sixteenth notes.
  \tuplet 5/4 { c''16( d'' e'' f'' g'') } a''4 g''2 |
  % Bar 3: grace notes do not add measured beats to the bar.
  \acciaccatura { c''16 d'' } f''4( e'' d'' f'') |
  d''2\trill b'2 | \break
  \barNumberCheck #5
  e''8( g'' e'' d'' c'' b' a' g') |
  % Bar 6: a sustained inner voice under an independent melody.
  << { a'4( c'' e''2) } \\ { e'1 } >> \oneVoice |
  \tuplet 3/2 { d''8( e'' f'') } e''4 d'' c'' |
  b'4( c''2.)\fermata |
  \barNumberCheck #9
  \bar "|."
}

leftHand = {
  \global
  \clef bass
  c,2 <e g c'>2 |
  f,2 <f a c'>2 |
  d,2 <f a d'>2 |
  g,2 <f g b>2 |
  \barNumberCheck #5
  c,2 <e g c'>2 |
  a,2 <e a c'>2 |
  g,2 <f g b>2 |
  <g, g>4 <c e g>2.\fermata |
  \barNumberCheck #9
  \bar "|."
}

dynamics = {
  s1\p | s1 | s1\< | s2 s2\! |
  s1\mp | s1 | s2\> s2 | s4 s2.\p |
}

\score {
  \new PianoStaff <<
    \new Staff = "upper" \rightHand
    \new Dynamics \dynamics
    \new Staff = "lower" \leftHand
  >>
  \layout { }
}
