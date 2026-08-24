# ----------------------------传感器信息提取 prompt1----------------------------
prompt1_1="""### Prompt
## Extra Information
### Sensor Types

- Acoustic (Acoustic signal)
  - Microphone
  - Ultrasonic Sensor
- Motion (Mechanical signal)
  - Accelerometer
  - Gyroscope
  - Vibration Sensor
  - Seismic Detector
- Force (Mechanical signal)
  - Pressure Sensor
  - Force Sensor
- Optical (Optical signal)
  - Image Sensor
  - Infrared Sensor
  - Lidar
  - Fingerprint Sensor
  - Millimeter Wave Radar
- Electromagnetic (Electromagnetic signal)
  - Touch Screen
  - Current Sensor
  - Voltage Sensor
- Thermal (Thermal signal)
  - Temperature Sensor
  - Humidity Sensor

# Input
- The attachment is the product specification sheet for this sensor model. 
- You are a sensor security expert.Please extract all information that may be related to sensor vulnerability, the more comprehensive and concise the better, avoiding redundancy.
- Please extract the information() into the following JSON format:
{
  "rag_input": "sensor type(detailed)+sensor model",
  "sensor_info": "
### Sensor Information   
- Sensor Types
- Sensor Models
- Sensor Structure
- All Product Parameters Potentially Involved in Sensor Vulnerability Testing(For example, circuit characteristics, electrical properties, measurement accuracy, noise levels, and environmental tolerance)",
}"""

# ----------------------------脆弱性机理分析 prompt3----------------------------
prompt3_1 = """# Prompt
            ## Extra Information
            ### Sensor Components 
            1. Transducer Module 
            - Acoustic Transducer: Converts Acoustic energy to Electrical energy.
            - Optical Transducer: Converts Optical energy to Electrical energy.
            - Electromagnetic Transducer : Converts Electromagnetic energy to Electrical energy.
            - Force Transducer: Converts Mechanical energy to Electrical energy.
            - Thermal Transducer : Converts Thermal energy to Electrical energy.
            2. Signal Conditioning Circuits
            - Amplifier 
            - Filter
            - ADC
            3. Computing and Communication Module 
            - DSP
            - Communication Interface 
            4. Auxiliary Module 
            - Power Supply 
            - Wires 
            - Clock Oscillator 
            #### Sensor Vulnerability Mechanism Taxonomy
    1. Saturation Effect: Primarily occurs in the sensor's transducer and signal conditioning circuits. It happens when the input signal exceeds the capacity of the transducer material or circuit elements. For transducers, for instance, the number of electron-hole pairs that can be generated in photovoltaic materials is limited, and high-intensity light exceeding its predefined amplitude range will saturate an optical sensor, leading to the maximum output. In signal conditioning circuits, it is generally caused by the supply voltage limitations in active circuit elements. When the input is an alternating current (AC) signal, symmetric saturation introduces harmonic distortion, while asymmetric saturation also introduces a direct current (DC) bias. This phenomenon is common in amplifiers, and is also posited to exist in filters and ADCs.
    2. Nonlinearity: Common in components such as the sensor's transducer and filters. It can be formulated as $f'(x)=a_{0}+a_{1}x + a_{2}x^{2}+cdots$. In practical cases, acoustic transducers and amplifiers are affected by nonlinearity, such as a modulated high-frequency signal being converted into a low-frequency output through a nonlinear effect; for example, an ultrasonic signal, which should be outside the microphone's acceptable frequency range, is converted into a detectable low-frequency signal by the microphone's acoustic transducer due to nonlinearity. Nonlinear rectification in amplifiers can also convert AC signals into DC offsets.
    3. Non-ideal Cutoff: Refers to the imperfect frequency response of the filter, which fails to effectively suppress signals in the stop-band. This can affect both the transducer and the signal conditioning circuits in a sensor. For instance, microphone transducers may respond to ultrasound, ultraviolet sensors may react to visible lasers, and low-pass filters may fail to eliminate stop-band frequencies, resulting in $|F^{prime}(omega)|>0(omega ge omega_{c})$ ($F'$ is the Fourier transform and $omega_{c}$ is the cutoff frequency). This allows signals that should not be detected to pass through the filter and affect the measurement results.
    4. Aliasing Effect: Occurs when ADCs receive input signals containing frequency components above the Nyquist frequency (i.e., $omega>omega_{s}/2$, where $omega_{s}$ is the sampling rate). The spectrum $F'(omega)$ then contains aliasing frequencies $omega_{a}=|omega - komega_{s}|$ ($k = round(omega / omega_{s})$). As a result, high-frequency signals are incorrectly interpreted as low-frequency components during sampling, effectively demodulating them into the measurement output and affecting the sensor's measurement accuracy.
    5. Resonance Effect: Occurs in the case of Acoustic-Cross-Field and Mechanical-Cross-Field. For acoustic signals, MEMS transducers used in motion sensors (such as accelerometers and gyroscopes) have inherent resonant frequencies. When external sound or ultrasound waves are near their resonant frequency, they can induce high-intensity interference, affecting the sensor's normal operation. Mechanical signals can also affect acoustic transducers through the Resonance Effect, such as injecting vibration signals directly into the diaphragm of an acoustic transducer, causing frequency injection. However, mechanical signals must propagate through rigid media, making their practical use for inducing OOB vulnerabilities less common.
    6. Photoacoustic Effect: A mechanism belonging to Optical-Cross-Field that affects sensors. Modulated light can cause the Photoacoustic Effect in the sensor, converting light energy into mechanical energy, generating mechanical vibrations, and thereby interfering with the sensor's normal measurement. Taking MEMS microphones as an example, they have been shown to respond to amplitude-modulated light. The modulated light causes the diaphragm structure of the MEMS microphone to vibrate, producing an output similar to $g_{2}(z)=A[1 + cos(omega_{o}+phi)]$ ($omega_{0}$ is the modulation frequency).
    7. Photoelectric Effect: Also an Optical-Cross-Field mechanism affecting sensors. This occurs when light liberates electrons from a material's surface, generating electric currents. Sensors with exposed conductive parts (such as MEMS barometers) are vulnerable to this effect, allowing attacks to induce an output bias under illumination, i.e., $g_{2}(z)=b$.
    8. Antenna Effect: Mainly occurs when Electromagnetic signals affect sensors. Conductive elements in the sensor (especially wires) act as unintended antennas, receiving ($g_{2}(z)$) or transmitting ($g_{1}(x)$) electromagnetic radiation. This effect is particularly pronounced when the conductor length approaches a quarter of the EM signal's wavelength, forming a resonant structure that efficiently couples EM energy into the circuit. This effect exists in components such as the transducer, amplifier input wires, ADC, and communication cables. Attackers can exploit it to inject malicious signals or capture sensitive information (snooping).
    9. Temperature Drift: Primarily reflects the temperature sensitivity of some sensor components, such as amplifiers and other analog circuits. Although Thermal-Cross-Field signals have not yet been directly exploited in attacks, due to the temperature sensitivity of these components, temperature changes may alter their performance and subsequently affect the sensor's measurement results."""

# 1. Saturation Effect
# 2. Nonlinearity
# 3. Non-ideal Cutoff
# 4. Aliasing 
# 5. Resonance Effect
# 6. Photoacoustic Effect
# 7. Photoelectric Effect
# 8. Antenna Effect
# 9. Temperature Drift

prompt3_4="""
## Key Insight
- **The same mechanism may exist in different components**.
- vulnerability identification must be grounded in:
1. Sensor hardware structure
2. Energy conversion path
3. Component-level physical limits

Note that you should start from the physical properties and hardware structure of the sensor to determine sensor vulnerabilities in a scientific and component-level manner. The following is an example of a vulnerability analysis based on a specific sensor model.

# Example: 1200TVL CCD Camera

## Sensor Structure Overview

The 1200TVL camera is a CCD-based imaging sensor consisting of:

- **CCD Array (Optical Transducer)** ： converts incident light into accumulated charge.
- Signal conditioning circuits（Amplifier、filter、ADC）
- **Charge Transfer and Readout Circuit**
- **Output Interface and Interconnect (PCB Traces / Power Lines)**

The measurand modality of this sensor is **Optical**, and the final output is an **electrical video signal**.

According to the SoK principle:
“Since the energy path ends in the electrical domain and produces valid output, a component-level vulnerability exists.”

## Mechanism-Level Reasoning
Consider in turn whether the attack can be successful using sound, light, and electromagnetic signals.
### Path A: Optical Saturation Path
High-intensity optical signal  
→ Photon absorption in **CCD photodiodes**  
→ Excessive charge accumulation  
→ Pixel full-well capacity exceeded  
→ Output voltage clipping  
→ Electrical video output (saturated image)
The energy remains within the intended modality (Optical), but the amplitude exceeds the design limit of the transducer.
This path ends in the electrical domain and produces a valid output signal.

### Path B: Electromagnetic Coupling Path (Antenna Effect)
High-frequency electromagnetic radiation  
→ Coupling into PCB traces / power lines  
→ Conductive structures act as unintended antennas  
→ Induced electrical interference  
→ Injected into signal conditioning circuit  
→ Electrical video output distortion
Here, electromagnetic energy is converted into electrical interference via unintended antenna behavior.
The energy path ends in the electrical domain and produces a valid output signal.

### Path C: Electromagnetic-Induced Amplifier Saturation
High-frequency electromagnetic radiation  
→ Antenna effect induces electrical signal  
→ Electrical interference injected into **Analog Front-End (Amplifier)**  
→ Voltage exceeds supply headroom  
→ Amplifier clipping / asymmetric saturation  
→ Distorted electrical video output
Although initiated by electromagnetic radiation, the final failure mechanism occurs in the electrical amplification stage.
The energy path again terminates in the electrical domain.

## Vulnerability Mechanism Analysis
| No. | Mechanism Name   | Source Component      | Detailed Description and Analysis |
| --- | ------------- | ----------- | ------ |
| 1   | **Saturation Effect**                  | **CCD Array (Optical Transducer)**          | The CCD photodiodes accumulate photo-generated charge proportional to incident light. When the optical amplitude exceeds the pixel full-well capacity, charge accumulation saturates, leading to voltage clipping in the readout stage. This is an **Optical-Amplitude Out-of-Range vulnerability** occurring within the intended modality. |
| 2   | **Antenna Effect**                  | **Interconnect (PCB Traces / Power Lines)** | Conductive traces and wiring unintentionally act as antennas under high-frequency electromagnetic radiation. The coupled EM energy is converted into electrical interference, forming an **Electromagnetic-Electrical Cross-Field vulnerability** at the interconnect level.                                                                |
| 3   | **Saturation Effect** | **Analog Front-End (Amplifier)**            | The amplifier has limited voltage headroom determined by supply constraints. Electromagnetically induced electrical signals may exceed this range, causing clipping or asymmetric saturation. This is an **Electrical-Amplitude Out-of-Range vulnerability** occurring in the signal conditioning stage.                                    |
"""

prompt3_5 = """
## Requirements:
- Considering one by one whether sound, light, and electromagnetic signals can successfully attack this sensor.
- Analyze the potential vulnerability mechanisms of different components one by one.
- A sensor(or a component) may have multiple vulnerability mechanisms；**The same mechanism may exist in different components** ；it is essential to analyze the sensor information to **identify all possible mechanisms**.
- The same mechanism can occur in different components, such as voltage amplitude saturation in a circuit and sound frequency saturation in a transducer. Please write these separately.
- Use plain language to explain the detailed description and analysis of the vulnerability mechanism, do not use the esoteric expressions from the extra information section.
Format(only one table):
### Vulnerability Mechanism Analysis 
| No. | Mechanism Name | Source Component | Mechanism (Name + Detailed Description and Analysis) |
|:---:|:---:|:---:|:---:|
| 1 | Mechanism Name 1 | Specific Sensor Component | **Mechanism Name**: Detailed description and analysis of the relevant mechanism|
| 2 | Mechanism Name 2 | Specific Sensor Component | **Mechanism Name**: Detailed description and analysis of the relevant mechanism|
| 3 | …… | …… | …… |
"""

# ----------------------------检测可能的脆弱性 prompt2----------------------------

prompt2_1 = """There are various vulnerabilities in the components of sensors, which we can refer to as sensor vulnerabilities. The knowledge below can be used as a reference for vulnerability testing
  ### Sensor Component-Level Vulnerability Taxonomy
  1. Out-of-Range
  (1) Definition: Out-of-range vulnerability represents the response of a sensor component to an input signal that lies within the **intended physical field** (modality), but falls outside the **intended operational range** in terms of amplitude or frequency.
  (2) Naming Convention:Use {Sensor Component Expected Modality}-{Amplitude/Frequency} Out-of-Range
  (3) Classification:
  - {Sensor Component Expected Modality}-Amplitude Out-of-Range: Occurs when the attack signal's amplitude exceeds the component's design limit, leading to the **saturation effect**. For transducers, this is limited by material constraints; for circuits, it is caused by supply voltage limitations.
  - {Sensor Component Expected Modality}-Frequency Out-of-Range: Occurs when the attack signal's frequency exceeds the intended bandwidth. This impacts output through **nonlinearity** (e.g., inter-modulation distortion), **non-ideal cutoff** of filters, or **aliasing effects** in ADCs.
  2. Cross-Field
  (1) Definition: In contrast to out-of-range vulnerabilities, cross-field vulnerabilities involve signal interactions across **different physical modalities**. They exploit unintended energy conversion principles to manipulate measurements or leak internal information.
  (2) Naming Convention:Use {Attack Modality at THIS component}-{Sensor Component Measurand Modality} Cross-Field. 
  (3) Classification :
  - Acoustic-{Sensor Component Measurand Modality} Cross-Field: Primarily affects **transducers** (especially MEMS structures). Acoustic waves near the **resonance frequency** of the mechanical sensitive element induce high-intensity internal interference.
  - Optical-{Sensor Component Measurand Modality} Cross-Field: Primarily affects **transducers** via two mechanisms:
      Photoacoustic Effect**: Light energy is absorbed by the **sensitive element's diaphragm**, converting into mechanical vibrations.
      Photoelectric Effect**: Light liberates electrons from **conductive elements** (like MEMS barometers) or **ASIC transistors**, inducing unintended currents.
  - Electromagnetic-{Sensor Component Measurand Modality} Cross-Field: Primarily affects **signal conditioning circuits** (amplifiers, ADCs) and **wiring**. Conductive elements act as unintended antennas via the **antenna effect**, coupling EM radiation into the electrical signal path.
  - Mechanical-{Sensor Component Measurand Modality} Cross-Field: Affects **acoustic transducers** (diaphragms) through the **resonance effect** when vibrations propagate through rigid media.
  - Thermal-{Sensor Component Measurand Modality} Cross-Field: Affects **amplifiers and analog circuits** within the signal conditioning stage via **temperature drift**, leading to output bias and parameter instability."""

prompt2_2 = """
# Example: Vulnerability Identification from Mechanisms (1200TVL CCD Camera)
The following example demonstrates how to determine the **vulnerability name** from an identified **mechanism**.  
For each mechanism, determine:
1. **Expected Modality** of the component  
2. **Attack Modality at THIS component**  
3. Use the taxonomy rules to determine the vulnerability name.

### Mechanism 1
**Mechanism:** Saturation Effect  
**Component:** CCD Array (Optical Transducer)
- Expected Modality: Optical  
- Attack Modality: Optical (high-intensity light)  
- Since the modality is the same but the amplitude exceeds the physical limit of the CCD pixel full-well capacity, the vulnerability is:
**Optical-Amplitude Out-of-Range**

### Mechanism 2
**Mechanism:** Antenna Effect  
**Component:** Interconnect (PCB Traces / Power Lines)
- Expected Modality: Electrical  
- Attack Modality: Electromagnetic radiation couples into conductive traces  
- The attack modality differs from the expected modality, therefore this is a cross-field interaction:
**Electromagnetic-Electrical Cross-Field**

### Mechanism 3
**Mechanism:** Saturation Effect  
**Component:** Analog Front-End (Amplifier)
- Expected Modality: Electrical  
- Attack Modality: Electrical (induced by electromagnetic coupling)  
- The signal exceeds the voltage headroom of the amplifier, causing clipping:
**Electrical-Amplitude Out-of-Range**

### Vulnerability Detection Result
| No. | Vulnerability Name | Mechanism Name ｜Source Component | Description | Judgment Reason |
|------|-------------------|-----|-------------|-------------|------------------|
| 1 | Optical-Amplitude Out-of-Range | Saturation Effect｜CCD Array | Excessive light saturates CCD pixel charge accumulation. | Attack modality equals expected modality but exceeds amplitude limit. |
| 2 | Electromagnetic-Electrical Cross-Field | Antenna Effect｜Interconnect | EM radiation couples into PCB traces acting as antennas. | Attack modality differs from the component's expected modality. |
| 3 | Electrical-Amplitude Out-of-Range | Saturation Effect｜Analog Front-End (Amplifier) | Electrical interference exceeds amplifier voltage range. | Electrical signal exceeds circuit amplitude limit. |
"""

prompt2_3 = """Referring to the vulnerability analysis example, please first determine the corresponding vulnerabilities based on the results of the mechanism analysis, and briefly describe each vulnerability, explaining the basis for your judgment.

Note:
1. Please confirm the vulnerability names corresponding to all previously identified mechanisms.It doesn't necessarily have to correspond to only one vulnerability; please list all possible vulnerabilities.
2. Please refer to the sensor vulnerability classification in the supplementary information section as much as possible. Your judgments must be accurate.

Format:
### Vulnerability Detection 
| No. | Vulnerability Name |Mechanism Name ｜Source Component | Description | Judgment Reason |
|------|-------------------|-----|-------------|-------------|------------------|
| 1    | Vulnerability 1   | Corresponding mechanism｜Specific Sensor Component | Explain what this vulnerability means in simple terms | How the model determines that the sensor has this (component-level)vulnerability from the mechanism |
| 2    | Vulnerability 2   | Corresponding mechanism｜Specific Sensor Component | Explain what this vulnerability means in simple terms | How the model determines that the sensor has this (component-level)vulnerability from the mechanism|"""



# 物理验证
# 请根据你的知识和已有的攻击案例中的参数，推断一个更加具体的攻击信号参数范围，并写进你的物理验证步骤中。参数范围越精确越好，但务必保证正确
# 英文版：
prompt4_1="""As a senior sensor hardware security expert, your task is to infer precise physical verification attack parameters（such as frequency, amplitude, intensity, etc.） based on sensor product specifications and known physical attack Mechanisms.

## Reasoning Framework (Must Follow):
1. For different vulnerabilities, derive the signal parameter ranges from key sensor datasheet parameters (sampling rate, bandwidth, sensitivity threshold, nonlinear compensation range, etc.) according to the corresponding physical mechanism.
2. You may leverage real data from RAG knowledge bases: sensors with similar product parameters usually exhibit similar sensitive signal parameters.
3. You may leverage the **Reasoning-Related Knowledge** listed below.
4. **Calibrate for environmental attenuation and hardware tolerances** by referencing similar models in the literature library (see Examples below) to provide parameter ranges within a specified margin of error. **Prioritizing accuracy, please be as precise as possible.The difference between the maximum and minimum values of the provided range should not exceed 5.**
---
## Reasoning-Related Knowledge (Non-exhaustive; you may extend based on your expertise)
### 1. Resonance Effect
* **Mechanism Definition:** External physical excitation (acoustic or vibration) matches the natural frequency of the sensor’s sensitive element (e.g., MEMS proof mass), inducing large mechanical displacement.
* **Key Sensor Parameters:** Mechanical resonant frequency ( f_r ), quality factor ( Q ), sampling rate ( f_s ).
* **Key Attack Signal Parameters:** Carrier frequency, amplitude, modulation mode (Sine, AM).
* **Attack Parameter Inference:**
  * **Fundamental resonance:** ( f_{attack} approx f_r ). For MEMS gyroscopes, this is typically in the kHz to tens of kHz range.
  * **Bandwidth constraint:** Attack frequency range is limited by the ( Q ) factor; frequency sweep step should be smaller than ( frac{f_r}{Q} ) to avoid missing the response peak.
  * **Target effect:** To induce a constant bias, saturation effects are often combined (see below); to cause oscillatory interference, use an unmodulated sine wave.
### 2. Saturation Effect
* **Mechanism Definition:** Input signal intensity exceeds the dynamic range of the transducer or conditioning circuit (e.g., amplifier), causing signal clipping.
* **Key Sensor Parameters:** Maximum linear input ( x_{max} ), supply voltage ( V_{cc} ).
* **Key Attack Signal Parameters:** Amplitude, carrier frequency.
* **Attack Parameter Inference:**
  * **Amplitude threshold:** ( A_{attack} > x_{max} ). For optical sensors, this appears as high-intensity laser illumination driving the output to full scale.
  * **DC bias inference:** Asymmetric saturation can convert AC interference into DC offset. If the goal is to alter static readings, amplitude must be increased into the nonlinear saturation region.
### 3. Nonlinearity Effect
* **Mechanism Definition:** Non-ideal transfer characteristics of amplifiers or transducers (e.g., quadratic terms) cause intermodulation distortion (IMD), demodulating high-frequency signals into in-band signals.
* **Key Sensor Parameters:** Second-order intercept point (IP2), in-band operating frequency ( f_{intext{-}band} ).
* **Key Attack Signal Parameters:** Carrier frequency ( f_c ), modulation frequency ( f_m ), modulation depth.
* **Attack Parameter Inference:**
  * **AM attack:** Use amplitude-modulated signals where the carrier ( f_c ) is ultrasonic or high-frequency EM, and the demodulated frequency ( f_m ) falls within the sensor’s in-band response (e.g., 20 Hz–20 kHz for microphones).
  * **Self-demodulation:** With a square-law term, an attack signal ( s(t) = A[1+m(t)]cos(2pi f_c t) ) generates low-frequency components containing ( m(t) ) at the output.
### 4. Non-ideal Cutoff
* **Mechanism Definition:** Insufficient stopband attenuation of sensors or front-end filters allows out-of-band signals (e.g., ultrasound for microphones) to pass.
* **Key Sensor Parameters:** Cutoff frequency ( f_c ), filter order (attenuation slope).
* **Key Attack Signal Parameters:** Frequency, amplitude.
* **Attack Parameter Inference:**
  * **Frequency selection:** ( f_{attack} > f_{cutoff} ). Even if designed for audible range, microphone transducers often respond up to ~40 kHz ultrasound.
  * **Power compensation:** Because the signal lies in the stopband, increase attack amplitude to compensate for filter attenuation ( H(f_{attack}) ), ensuring sufficient residual signal reaches downstream circuitry.
### 5. Aliasing Effect
* **Mechanism Definition:** Failure of the anti-aliasing filter before the ADC causes signals above half the sampling rate to fold into low-frequency artifacts.
* **Key Sensor Parameters:** Sampling rate ( f_s ), ADC resolution.
* **Key Attack Signal Parameters:** Frequency, initial phase.
* **Attack Parameter Inference:**
  * **Folding frequency:** ( f_{alias} = |f_{attack} - k cdot f_s| ).
  * **Parameter tuning:** Adjust ( f_{attack} ) so that ( f_{alias} ) falls within sensitive system control loops (e.g., UAV flight controller loops).
### 6. Photoacoustic Effect
* **Mechanism Definition:** Amplitude-modulated laser illumination heats opaque materials (e.g., microphone diaphragms), causing thermal expansion and contraction that induces mechanical vibration.
* **Key Sensor Parameters:** Diaphragm structure, material absorption rate, thermal relaxation time.
* **Key Attack Signal Parameters:** Modulation frequency ( f_m ), average power, laser wavelength.
* **Attack Parameter Inference:**

  * **Modulation matching:** Laser must be amplitude-modulated; ( f_{modulation} ) should equal the target audio or control signal frequency.
  * **Wavelength selection:** Choose wavelengths with high enclosure transmissivity and high internal diaphragm absorption (e.g., near-infrared).

### 7. Photoelectric Effect
* **Mechanism Definition:** Photon illumination of semiconductor PN junctions or circuit traces generates electron–hole pairs, inducing photocurrent or altering transistor bias.
* **Key Sensor Parameters:** Exposed PN junction area, bandgap energy.
* **Key Attack Signal Parameters:** Laser wavelength (photon energy), DC intensity.
* **Attack Parameter Inference:**
  * **Energy threshold:** Photon energy ( E = frac{hc}{lambda} ) must exceed the semiconductor bandgap (e.g., 1.1 eV for silicon), corresponding to visible or near-infrared light.
  * **Attack modes:** DC laser to induce output bias or logic flips; high-frequency pulsed light to disrupt digital communications (e.g., SPI/I²C).

### 8. Antenna Effect
* **Mechanism Definition:** Internal traces or external pins unintentionally act as antennas, coupling RF electromagnetic interference (EMI) into circuits.
* **Key Sensor Parameters:** Trace length ( L ), characteristic impedance, common-mode rejection ratio (CMRR).
* **Key Attack Signal Parameters:** Frequency (wavelength), polarization, modulation mode (typically sine wave).
* **Attack Parameter Inference:**
  * **Efficient coupling:** When ( L approx frac{lambda}{4} ), coupling efficiency is maximized. For centimeter-scale pins, attack frequencies typically range from hundreds of MHz to several GHz.
  * **Conducted vs. radiated EMI:** Radiated EMI requires finding specific coupling frequencies via sweep (white-box); conducted EMI injects via power or ground lines.

### 9. Thermal Drift
* **Mechanism Definition:** External thermal radiation alters sensor component temperature, changing semiconductor properties (bandgap, carrier concentration) and causing offset or gain drift.
* **Key Sensor Parameters:** Temperature coefficient (TCO/TCS), thermal resistance, heat capacity.
* **Key Attack Signal Parameters:** Thermal power, duration.
* **Attack Parameter Inference:**
  * **Low-frequency nature:** Due to thermal inertia, temperature attacks have very low bandwidth (<1 Hz); inference focuses on irradiation duration to accumulate sufficient heat for measurable bias.
  * **Targeting:** Directional heat sources aimed at temperature-sensitive analog front-end circuits.

---

## Examples

### [Example1]
* **Sensor:** Gyroscope MPU6050
* **Datasheet Parameters:** Mechanical resonant frequencies
  | Axis       | Min | Typ | Max | Unit |
  | ---------- | --- | --- | --- | ---- |
  | **X-Axis** | 30  | 33  | 36  | kHz  |
  | **Y-Axis** | 27  | 30  | 33  | kHz  |
  | **Z-Axis** | 24  | 27  | 30  | kHz  |
* **Attack Signal Modality:** Acoustic
* **Attack Type:** Acoustic-to-mechanical cross-field
* **Attack Mechanism:** Resonance effect
* **Attack Signal Parameter:** 25.928 kHz
* **Analysis:** External acoustic excitation matches the proof-mass natural frequency; 25.928 kHz lies within this range.

### [Example2]
* **Sensor:** CMOS camera IMX219
* **Datasheet Parameters:** Square pixel array
* **Attack Signal Modality:** Laser
* **Attack Type:** Optical energy – amplitude ou-of range
* **Attack Mechanism:** Saturation effect
* **Attack Signal Parameter:** Sufficiently high optical intensity
* **Analysis:** Any laser with sufficient intensity can successfully saturate the camera.

### [Example3]
* **Sensor:** CMOS camera
* **Datasheet Parameters:** Unknown
* **Attack Signal Modality:** Electromagnetic
* **Attack Type:** Electromagnetic–optical cross-field
* **Inferred Attack Parameters:**
  * Frequency: 32.5 MHz (identified via frequency sweep to match cable resonance)
  * Amplitude: ~3 W (RF power amplifier)
  * Modulation: Sine wave (attack signal)
  * Proximity: Magnetic probe placed ~2 cm from the sensor–microcontroller data cable

* **Derivation Logic:** Attack effectiveness increases with injected power and frequency alignment to cable resonance. 32.5 MHz was identified via resonance scanning. The injected EM signal perturbs digital signal levels, causing bit errors. Actual success rate depends on routing, shielding, coupling, and distance; stronger coupling (closer probe, higher power) increases bit-flip likelihood."""

prompt4_2="""
** task**
- For each of the vulnerabilities mentioned above, please provide detailed steps and data on how to verify whether this vulnerability exists.
- The external signal used by the attacker must be feasible; for example, the attacker cannot input a high voltage into the sensor.
- Using signals such as sound, light, or electromagnetic signals is more reasonable.
- MUST follow the specified TABLE format:
### Physical Verification
In order to ensure that the proposed vulnerabilities indeed exist in your device, the following are the detailed physical verification steps and details generated for each vulnerability:
| No. | Vulnerability Name | Required Testing Equipment |Attack signal parameter range(External signals used by attackers)| Testing Steps and Data | Expected Result |Reasoning for parameter inference|
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | Vulnerability Name 1 | [List of Equipment, marked by number] | (List all required parameters；the more precise, the better;The difference between the maximum and minimum values of the provided range should not exceed 5.)|1. [Step One]<br>2. [Step Two]<br>... | [Describe the expected test result] |[Provide reasoning for parameter inference，Provide real data and references as support]|
| 2 | Vulnerability Name 2 | [List of Equipment, marked by number] | (List all required parameters；the more precise, the better;The difference between the maximum and minimum values of the provided range should not exceed 5.)|1. [Step One]<br>2. [Step Two]<br>... | [Describe the expected test result] |[Provide reasoning for parameter inference，Provide real data and references as support]|
....(Each vulnerability requires detailed physical verification steps and data.)
"""

system_prompt = "You are a professional security analyst specializing in sensor vulnerabilities. Your task is to analyze sensor product manuals to identify potential vulnerabilities, understand their underlying mechanisms, and provide actionable testing strategies. Use your expertise in sensor technology and security to deliver accurate and insightful assessments."
