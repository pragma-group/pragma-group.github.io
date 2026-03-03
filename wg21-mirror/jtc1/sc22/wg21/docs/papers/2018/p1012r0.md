|                |                                                   |
|----------------|---------------------------------------------------|
|Document Number:| P1012R0                                           |
|Date:           | 2018-04-02                                        |
|Project:        | Programming Language C++                          |
|Reply-to:       | Frank Zingsheim `<f dot zingsheim at gmx dot de>` |
|Audience:       | Evolution                                         |

# Proposal Ternary Right Fold Expression

### *Revision 0*

## I. Motivation
### A) Use case
The following example shows a simple use case of a ternary right fold expression.

Consider a function `f` with an index based template parameter:
```
#include <cstddef>

class T;

template <std::size_t i>
T f();
```
The task is now to write a function which calls the appropriate template function for a run time index `j` which has a compile time maximal index `(n-1)`. If `j` is out of bounds an exception should be thrown.

With the proposal from this document it would be possible to write this as follows.
```
#include <functional>
#include <stdexcept>

template <typename T>
T throw_range_error()
{
    throw std::range_error("Out of range");
}

template <std::size_t... is>
T test_impl(std::size_t j, std::index_sequence<is...>)
{
    return ( (j == is) ? f<is>() : ... : throw_range_error<T>() );
}

template <std::size_t n>
T test(std::size_t j)
{
    return test_impl(j, std::make_index_sequence<n>());
}

```

If the implementer of the method is sure that the index `j` is below `n` the function `test_impl` can also be written like follows without a trailing `throw_range_error` call.
```
template <std::size_t... is>
T test_impl(std::size_t j, std::index_sequence<is...>)
{
    return ( (j == is) ? f<is>() : ... );
}

```

### B) Consistent Completion of Fold Expressions
The proposed syntax is a canonical extension of the already existing fold expression for binary operators [1].
The right fold expansion is applicable to any binary operator which return value can be used as a right argument of the same binary operator.

Since for the conditional ternary operator the return value of the operator can be used as a right argument of the conditional ternary operator, the conditional ternary operator can be expanded in a right fold expression, consistently.

## II. Proposed Expansion of Ternary Fold Expression
Only right fold expressions are supported for the conditional ternary operator. Left fold expressions are **not** supported for the conditional ternary operator.

Let `C` denote a non-expanded parameter pack which expand to conditions.
Let `E` denote a non-expanded parameter pack of the same size as `C`.
Let `I` denote an ordinary expression.

### A) Ternary Right Fold Expression with Initial Value
The following fold expression
```
( C ? E : ... : I )
```
expands to
```
( C(1) ? E(1) : ( ... ( C(N-1) ? E(N-1) : ( C(N) ? E(N) : I ) ) ) )
```
The limiting case `N = 0` evaluates to `( I )`.

### B) Ternary Right Fold Expression without Initial Value

The following fold expression
```
( C ? E : ... )
```
expands to
```
( C(1) ? E(1) : ( ... ( C(N-2) ? E(N-2) : ( C(N-1) ? E(N-1) : E(N) ) ) )
```
Note: The n-th conditional `C(N)` is **not** evaluated.

`N` has to be greater or equal to `1`.

The limiting case `N = 1` evaluates to the unconditional evaluated `( E(N) )`

## III. Further Example Use Case
Suppose, one has a collection of translation classes defined as follows.
```
#include <string>
#include <string_view>

struct german
{
    static constexpr char language[] = "German";
    static std::string translate_to_english(
        std::string_view text);
};

struct french
{
    static constexpr char language[] = "French";
    static std::string translate_to_english(
        std::string_view text);
};

struct spanish
{
    static constexpr char language[] = "Spanish";
    static std::string translate_to_english(
        std::string_view text);
};

```
The supported languages are known at compile time.
The task is now to write a function which calls the correct translation with a language string given at run time.

This task could be solved with ternary fold expression from this proposal like follows.
```
#include <stdexcept>

template <typename T>
T throw_unknown_language(std::string language)
{
    throw std::runtime_error("Unknown language: " + language);
}


template<class... translators>
std::string translate_to_english_impl(
    std::string_view language,
    std::string_view text)
{
    return ( language == translators::language
             ? translators::translate_to_english(text)
             : ... : throw_unknown_language<std::string>(
                         std::string(language)) );
}

std::string translate_to_english(
    std::string_view language,
    std::string_view text)
{
    return translate_to_english_impl<german, french, spanish>(
        language,
        text);
}
```

## IV Naming Convention
### A) Existing Names for Fold Expressions on Binary Operators
In the current C++ Standard the fold expressions on binary operators `op` with a pack expansion parameter `E` and an optional initial expression `I` are defined as follows.

* `( E op ... )` unary right fold
* `( ... op E )` unary left fold
* `( E op ... op I )` binary right fold
* `( I op ... op E )` binary left fold

### B) Possible Names for Fold expressions on the Ternary Operator
In the following different naming conventions are proposed. The author does not have a clear preference for one convention.

#### 1. Ternary Fold

* `( C ? E : ... )` unary right ternary fold
* `( C ? E : ... : I )` binary right ternary fold

This naming is confusing due to *binary right ternary*.
Is the expression *binary* or *ternary*?

#### 2. Conditional Fold

* `( C ? E : ... )` unary right conditional fold
* `( C ? E : ... : I )` binary right conditional fold

This naming is confusing since it suggests that the folding might be conditional.

#### 3. Naming according to the used number of parameter

* `( C ? E : ... )` binary right fold
* `( C ? E : ... : I )` ternary right fold

This naming is not unique, since binary right fold is used for binary operators as well as ternary operators, but in a different context.


#### 4. Fold with and without Initializer

This would need a rename of the existing fold expansions, i.e.

* `( E op ... )` binary right fold without initial value
* `( ... op E )` binary left fold without initial value
* `( E op ... op I )` binary right fold with initial value
* `( I op ... op E )` binary left fold with initial value
* `( C ? E : ... )` ternary right fold without initial value
* `( C ? E : ... : I )` ternary right fold with initial value

This naming is confusing because it renames the existing unary fold expressions to binary fold expressions.

## V Design Decisions

### A) On the Non-Evaluation of the Last Condition In the Right Fold Expression without Initial Value

In the fold expression `( C ? E : ... )` the parameter pack `C` and `E` have to be of the same size. The n-th condition `C(N)` is not evaluated. This paragraph discusses these design decision.

1) In many cases `C` and `E` are assembled from the same parameter pack. Therefore, the parameter packs `C` and `E` of the same size should be supported. 

2) If the n-th condition `C(N)` would be evaluated then something has to be executed in case `C(N)` evaluates to false. The only thing which could be done in this case is throwing an exception. In case the user has checked that one of the conditions is already checked this contradicts the principle 'only pay for what you use'. In case the programmer has not checked the conditions before the programmer still can use the ternary fold expression with initial value, i.e. `( C ? E : ... : I )` and handle the error in the `I` expression.

3) Additional to the parameter pack `C` and `E` being of the same size one could also support the case of `C` being of size `N-1` whereas `E` is of the size `N`. In this case there would not be a condition `C(N)` which is not evaluated.

## VI Revision History

 * Revision 0: Initial Proposal

## VII References
* [1] Programming Languages - C ++, ISO/IEC
14882:2017(E), 8.1.6 Fold expressions [expr.prim.fold]
* [2] GitHub repository of this document <https://github.com/zingsheim/ProposalTernaryFold>
