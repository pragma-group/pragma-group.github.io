Document No: P1421r0 <br>
Date: 2019-01-18 <br>
Author: Andrzej Krzemie&#x0144;ski <br>
Reply-to: akrzemi1 (at) gmail (dot) com <br>
Audience: EWG


Assigning semantics to different Contract Checking Statements
=============================================================

Motivation
----------

This paper provides some perspective on the recent issues around Contract Programming support in C++. While the authors of
[[p0542r5]](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2018/p0542r5.html) work on the compromise solution, this paper
tries to give some insigths into where the problems come from.

The conclusion is that there are more 'circumstances' that can affect what semantics (ignore, run-time check, assume) we want to
associate with different Contract Checking Statements (CCS) in different places in code than what [[p0542r5]](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2018/p0542r5.html) proposes or even what the *roles* as defined in [[P1332R0]](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2018/p1332r0.txt) offer. While it might be impractical to put all these circumstances as requirements in the Standard, what the Standard could do is to allow provision for implementation-defined additional control over the semantics assigned to CSS-es in a program. 


What should affect the CCS semantics
------------------------------------

In the following description, when referring to concrete semantics rendered by CCS-es and 
build configuration, we use terms defined in [[R1333R0]](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2018/p1333r0.txt):

* "ignore" -- validate syntax correctness and otherwise ignore: no assumptions, no optimizations, no run-time checks
* "assume" -- no run-time checks; eliminate branches in front of and behind the CSS that would be taken only if the condition in the CSS were to be violated. This is referred to as CCS-based optimization.
* "check (never continue)" -- perform run-time checks; compiler is allowed to assume that control never gets past the CSS if the condition is evaluated to false.
* "check (always continue)" -- perform run-time checks; compiler is allowed to assume that control always gets past the CSS, even if the condition is evaluated to false.
* "check (maybe continue)" -- perform run-time checks; compiler can assume if control gets or not past the CSS in case cthe consition is evaluated to false.

What particular semantics gets chosen for different CCS-es can be controlled by a number of things:
* Purpose of the binary: for testing, debugging, or release.
* CCS's intended 'puprpose' stated in the CSS, "evaluate to prevent UB", vs "evaluate to check what happens" vs "just indicate unimplementable condition".
* Predicted cost of evaluating the check.
* Our confidence of CSS's condition being satisfied in the program.
* Whether it is a precondition or a postcondition/assertion.

Concepts in [[p0542r5]](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2018/p0542r5.html), CCS "level" or "continuation mode" are not able to model programmer expectations.


Canonical assertion levels
--------------------------

[[p0542r5]](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2018/p0542r5.html) lists three assertion levels: Default, Audit and Axiom. Along with the notion of "build level" this gives an impression that these three can be positioned on a one-dimensional scale. But they are not one dimensional. Yes, Default and Audit indeed seem to differ only by "weight", but Axiom is different in quality than the former two. People have expressed requirements and expectations that do not fit into this model. Let's first have a closer look at these three levels.


### Default

Code after the CCS *depends* on the condition to be true (potentially UB if control gets past the CCS with violated condition).

This does not necessarily mean that something needs to be "protected against UB". In a correct program paths are executed only with values that do not violate the CSS conditions. All five concrete semantics make sense for this "level" of assertion.


### Audit

Same as *Default* but we have reasons to believe that checking it at runtime will noticeably affect program performance. We give this additional "hint" as to our intentions: maybe do not execute them if you care about performance.

Problem described in [[P1321r0]](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2018/p1321r0.html) might imply that there are some interactions between semantics assigned to *Default* and *Audit* CCS-es: if we apply "assume" semantics to *Audit* and "check" semantics to *Default*, this checking may be compromized by the optimizations. But this only appears this way in the context of [[p0542r5]](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2018/p0542r5.html) under which you can either "check" the the condition or "assume" it, but you cannot "ignore" it. [[P1290r0]](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2018/p1290r0.pdf) tries to fix the problem by requiring that you can either "check" or "ignore" a condition, but you cannot "assume" it. While this is an improvement, it unnecessarily prevents CCS-based assumptions. 

At some point I may want the compiler to make assumptions based on my CSS-es. [[P1290r0]](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2018/p1290r0.pdf) cannot guarantee that because it is confined to this linear model. The fact that [[P1290r0]](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2018/p1290r0.pdf) allows assumptions on *Axiom* checks does not help here, because I want the same CSS to be sometimes evaluated and sometimes assumed.

And obviously: modifying the code by applying a CSS-based assumption affects the program and affects other CSS-es. That is the point of assumptions. Therefore programmers would only allow assumptions on the selected CSS-es. Not "every single one with *Audit* level". The problem in [[P1321r0]](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2018/p1321r0.html) was that CCS cannot be just ignored. 


### Axiom

Same as *Default* except that even evaluating the CSS condition at runtime would have correctness impact on the program 
(broken preconditions, UB, etc.), or is impossible (program would not compile). 

The range of semantics is reduced: we cannot evaluate the checks at run-time.

Note that the same interaction between *Axiom* and *Default* (and *Audit*) exists: If we apply "assume" semantics to *Axiom* and at the same time apply "check" semantics *Default* or/and *Audit*, this checking may be compromized by the optimizations. But as we indicated above, that is the point of assumptions.

The idea that Axiom* CSS-es are better suited for "assume" semantics than *Default* or *Audit* is wrong.
Only because I have said that my algorithm expects iterators `f` and `l` to represent a valid range, it does not mean that 
the compiler should use this as an assumption in other places. Such expectation is no more "reliable" than expectation in *Axiom* and *Default* CSS-es. It is just that we cannot evaluate the condition: nothing more.

The ability to enable assumptions for all *Axiom* CSS-es, as offered in [[P1290r0]](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2018/p1290r0.pdf) is not a satisfactory solution either. I will typically want to enable assumptions for some *Axioms*: no all of them. I know and trust my CSS-es. I cannot make that call for CSS-es in the libraries I include.


Other possible non-linear classification of CSS-es 
---------------------------------------------------

If we depart from treating  *Default* and *Audit* and *Axiom* as levels on a one-dimensional scale, we can identidy more CCS "hints":

### Guarantee

CCS guarantees that the condition holds. This is possible if the author is in control of the preceeding code. This is similar to GCC's or Clang's `__builtin_unreachable()`.

This role is most likely to be assigned semantics "assume".

This 'kind' makes sense for asserts and postconditions, but not really for precondiitons: you usually are not in control of your callers.


### Review

The code after the CCS does *not* depend on the condition. The goal is to have a place to evaluate the condition, and record the fact of failure, but otherwise not to affect the program.

The most likely semantics are "check" or "ignore". Of course, "assume" semantics, in *Default* (or in fact, any other) "kind" can affect these semantics. In the end, this is the point of "assume": that code can be generated differently based on the new information.


### Review + audit

Same as *Review* but there are reasons to believe that the evaluation of the condition will noticeably impact program performance.


### More...

One can imagine more such "hints". For instance, assertion costs can be finer grained than just *Default* and *Audit*. One could imagine three cost categories:

* Where assertion overhead is negligible compared to the containing function.
* Where assertion overhead is simialr to the function overhead (program slowdown by factor 2).
* Where assertion overhead has bigger complexity that the function.

Also "relatively fast" (that would qualify fo *Default* "level") is subjective and authors of different libraries can set the thresholt differently. The programmer may disagree with the decision in some of the libraries. Therefore there may be a need to enable *Default* assertions per-library (per module, per namespace, per tag in the assert).

The orthogonal division of CCS-es into levels and roles, as in 
[[P1332r0]](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2018/p1332r0.txt) also does not quite cut it. While it makes sense to have an *Audit* version of a *Review* assert, an *Axiom* version does not seem to make sense.

The passage of time
-------------------

Sometimes a different semantics can be assigned to a CSS only because some time has passed. For a group of CSS-es in my library, I want to treat them as *Review* for some time, i.e., just evaluate, log and continue. But later, when I get confidence that the CSS-es are called in-contract, I may want to evaluate and throw on failure. And do this not for all *Review* CSS-es but only fo a subset from one library. Therefore changing semantic for all *Review* CSS-es will not cut it either.


Preconditions vs other CCS-es
-----------------------------

It is a common situation in contract checking frameworks to runtime check only preconditions but ignore assertions, postconditions and invariants. E.g, this is possible in Eiffel
([[EIFFEL]](https://www.eiffel.org/doc/eiffel/ET-_Design_by_Contract_%28tm%29%2C_Assertions_and_Exceptions)) and in Boost.Contract ([[BOOST.CONTRACT]](https://www.boost.org/doc/libs/1_69_0/libs/contract/doc/html/index.html)).
The reason for this is that the likelihood of detecting a bug while evaluating a precondition is much much higher than in other types of CCS-es. This is because preconditions are the only type of CCS-es where a different person declares the expectation and a different person is expected to fulfill it: the likelihood of micommunication is higher. In contrast, for postconditions, the author of the function declares the precondition and implements the function body.

Therefore it is likely that programmers will want only preconditions to be evaluated at run-time.


Different handlers and different continuation modes within ne program
---------------------------------------------------------------------

There may be a need to use more than one continuation mode in the program: continue after some failed assertions but make sure to abort on others. Similarly different callbacks may be needed for different assertions. This could be implemented through one callback that obtains sufficient input to determine what level/mode/role/intention/kind of a CCS has failed.


Recommendation
--------------

1. As per [[R1333r0]](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2018/p1333r0.txt), define the five semantics of CSS-es in the Standard.

2. As suggested in [[P1332r0]](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2018/p1332r0.txt) (section 5.4.2), provide a slightly different syntax for naming the returned object, e.g.: `[[ensures(r): r >= 0]]`. This is in order to easily say if a given identifier represents the assertion level/hint or a variable in a postcondition.

3. Apart from `default`, `audit` and `axiom` allow arbitrary identifier or namespace-qualified identifier in that position. Don't call them "levels" but something else, like "tags". These identifiers are passed to the violation handler if run-time checking is requested.

4. Add a provision in the standard that, apart from these mandated in the Standard, there are implementation-defined ways to map CSS-es onto semantics that may include the tag, kind (precondition vs postcondition), enclosing namespace, translation unit. If some CCS tag is not recognized by the implementation, it should apply "ignore" semantics. 


References
----------

[[p0542r5]](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2018/p0542r5.html) G. Dos Reis, J. D. Garcia, J. Lakos, A. Meredith, N. Myers, B. Stroustrup, "Support for contract based programming in C++".

[[P1290r0]](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2018/p1290r0.pdf) J. Daniel Garcia, "Avoiding undefined behavior in contracts".

[[P1321r0]](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2018/p1321r0.html) Ville Voutilainen, "UB in contract violations".

[[P1332r0]](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2018/p1332r0.txt) Joshua Berne, Nathan Burgers, Hyman Rosen, John Lakos, "Contract Checking in C++: A (long-term) Road Map".

[[R1333r0]](http://www.open-std.org/jtc1/sc22/wg21/docs/papers/2018/p1333r0.txt) Joshua Berne, John Lakos, "Assigning Concrete Semantics to Contract-Checking Levels at Compile Time".

[[EIFFEL]](https://www.eiffel.org/doc/eiffel/ET-_Design_by_Contract_%28tm%29%2C_Assertions_and_Exceptions) Eiffel Tutorial: "Design by Contract (tm), Assertions and Exceptions".

[[BOOST.CONTRACT]](https://www.boost.org/doc/libs/1_69_0/libs/contract/doc/html/index.html) Lorenzo Caminiti, Boost.Contract.
