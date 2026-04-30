# Core Source Code Files

## run.sh
Main launch script. Runs people follower and voice communication in parallel with logging.

## test_FB_first.py
Vision-based people follower controller. Handles human body detection and PID control, then sends movement commands (F/B/L/R/LL/RR/S/A) via serial port to Arduino (i.e., `non_PID_slow.ino`) for motor execution.

## non_PID_slow.ino
Arduino firmware. Receives serial commands from the Jetson and controls 4WD motors via PWM.

## voice_llm_speaker.py
Voice communication. Handles wake word detection, speech-to-text transfer, LLM conversation, and speech output.

## important_actions.txt
Documentation of key system commands and API configuration.
