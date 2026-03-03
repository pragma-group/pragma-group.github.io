//=============================================================================
// This is a program to measure the relative efficiency of qsort vs std::sort
// and of function objects vs function pointers.
//
// Optional Arguments: number of iterations to repeat
//                     size of array of doubles to sort
//                     name of output file
//
// In all cases, an array of doubles is filled with random numbers.
// This array is sorted in ascending order, then the same random numbers are
// reloaded into the array and sorted again. Repeat ad libitum.
//
//
// What is measured:
// These measurements operate on an array of doubles
// 1. Using qsort + user-defined comparison function to sort array
// 2. Using std::sort + a function pointer (not a function object)
// 3. Using std::sort + user-defined function object, out-of-line code
// 4. Using std::sort + user-defined function object, inline code
// 5. Using std::sort + std::less
// 6. Using std::sort + native operator <
//
// These measurements operate on an std::vector of doubles
// instead of a primitive array
//
// 7. Using std::sort + std::less
// 8. Using std::sort + native operator <
// 9. Using std::sort + function pointer from test 2
//
//
// Since qsort's comparison function must return int (less than 0, 0, greater than 0)
// and std::sort's must return a bool, it is not possible to test them with each
// other's comparator.

//=============================================================================
// struct to hold identifier and elapsed time
struct T {
    const char* s;
    double t;

    T(const char* ss, double tt) : s(ss), t(tt) {}
    T() : s(0), t(0) {}
};

// ---------  helper functions --------------------------------------------
// qsort passes void * arguments to its comparison function,
// which must return negative, 0, or positive value

int
less_than_function1( const void * lhs, const void * rhs )
{
    int retcode = 0;
    if( *(const double *) lhs < *(const double *) rhs ) retcode = -1;
    if( *(const double *) lhs > *(const double *) rhs ) retcode = 1;
    return retcode;
}

// std::sort, on the other hand, needs a comparator that returns true or false
bool
less_than_function2( const double lhs, const double rhs )
{
    if( lhs < rhs ) return true;
    else return false;
}


// the comparison operator in the following functor is defined out of line
struct less_than_functor
{
    bool operator()( const double& lhs, const double& rhs ) const;
};

bool
less_than_functor::operator()( const double& lhs, const double& rhs ) const
{
    return( lhs < rhs? true : false );
}

// the comparison operator in the following functor is defined inline
struct inline_less_than_functor
{
    bool operator()( const double& lhs, const double& rhs ) const
    {
       return( lhs < rhs? true : false );
    }
};


// ----------------------------------------------------------------------------
#include <vector>
#include <functional>
#include <algorithm>
#include <iostream>
#include <fstream>
#include <ctime>
#include <stdlib.h>

using namespace std;

int main(int argc, char* argv[])
{

    int i;

    int iterations = (1 < argc) ? atoi(argv[1]) : 1000000;  // number of
                                                           // iterations
    int tablesize = (2 < argc) ? atoi(argv[2]) : 1000000;  // size of
                                                    // array

    ofstream target;
    ostream* op = &cout;
    if (3 < argc) {  // place output in file
        target.open(argv[3]);
        op = &target;
    }
    ostream& out = *op;


    // output command for documentation:
    for (i = 0; i < argc; ++i)
        out << argv[i] << " ";
    out << endl;

    vector<T> v;                        // holds elapsed time of the tests

    // seed the random number generator
    srand( clock() );
    clock_t t = clock();
    if (t == clock_t(-1))
    {
        cerr << "sorry, no clock" << endl;
        exit(1);
    }

    // initialize the table to sort. we use the same table for all tests,
    // in case one randomly-generated table might require more work than
    // another to sort
    double * master_table = new double[tablesize];
    for( int n = 0; n < tablesize; ++n )
    {
        master_table[n] = static_cast<double>( rand() );
    }

    double * table = new double[tablesize];                // working copy

    // here is where the timing starts
    // TEST 1: qsort with a C-style comparison function
    copy(master_table, master_table+tablesize, table);
    t = clock();
    for (i = 0; i < iterations; ++i)
    {
        qsort( table, tablesize, sizeof(double), less_than_function1 );
        copy(master_table, master_table+tablesize, table);
    }
    v.push_back(T("qsort array with comparison function1         ", clock() - t));


    //TEST 2: std::sort with function pointer
    copy(master_table, master_table+tablesize, table);
    t = clock();
    for (i = 0; i < iterations; ++i)
    {
        sort( table, table + tablesize, less_than_function2 );
        copy(master_table, master_table+tablesize, table);
    }
    v.push_back(T("sort array with function pointer              ", clock() - t) );

    // TEST 3: std::sort with out-of-line functor
    copy(master_table, master_table+tablesize, table);
    t = clock();
    for (i = 0; i < iterations; ++i)
    {
        sort( table, table + tablesize, less_than_functor() );
        copy(master_table, master_table+tablesize, table);
    }
    v.push_back(T("sort array with user-supplied functor         ", clock() - t));

    // TEST 4: std::sort with inline functor
    copy(master_table, master_table+tablesize, table);
    t = clock();
    for (i = 0; i < iterations; ++i)
    {
        sort( table, table + tablesize, inline_less_than_functor() );
        copy(master_table, master_table+tablesize, table);
    }
    v.push_back(T("sort array with user-supplied inline functor  ", clock() - t));

    //TEST 5: std::sort with std::<less> functor
    copy( master_table, master_table+tablesize, table );
    t = clock();
    for (i = 0; i < iterations; ++i)
    {
        sort( table, table + tablesize, less<double>() );
        copy(master_table, master_table+tablesize, table);
    }
    v.push_back(T("sort array with standard functor              ", clock() - t));

    //TEST 6: std::sort using native operator <
    copy( master_table, master_table+tablesize, table );
    t = clock();
    for (i = 0; i < iterations; ++i)
    {
        sort( table, table + tablesize );
        copy(master_table, master_table+tablesize, table);
    }
    v.push_back(T("sort array with native < operator             ", clock() - t));


    //TEST 7: std::sort with std::less functor,
    //     on a vector rather than primitive array
    vector<double> v_table(  master_table, master_table+tablesize );
    t = clock();
    for (i = 0; i < iterations; ++i)
    {
        sort( v_table.begin(), v_table.end(), less<double>() );
        copy( master_table, master_table+tablesize, v_table.begin() );
    }
    v.push_back(T("sort vector with standard functor             ", clock() - t));

    //TEST 8: std::sort vector using native operator <
    v_table.assign(  master_table, master_table+tablesize );
    t = clock();
    for (i = 0; i < iterations; ++i)
    {
        sort( v_table.begin(), v_table.end() );
        copy( master_table, master_table+tablesize, v_table.begin() );
    }
    v.push_back(T("sort vector with native < operator            ", clock() - t));


    //TEST 9: std::sort vector using function pointer from test 2
    v_table.assign(  master_table, master_table+tablesize );
    t = clock();
    for (i = 0; i < iterations; ++i)
    {
        sort( v_table.begin(), v_table.end(), less_than_function2 );
        copy( master_table, master_table+tablesize, v_table.begin() );
    }
    v.push_back(T("sort vector with function pointer             ", clock() - t));


    if (clock() == clock_t(-1))
    {
        cerr << "sorry, clock overflow" <<endl;
        exit(2);
    }

    // output results
    out << endl;
    for (i = 0; i < v.size(); i++)
        out << v[i].s << " :\t"
            << v[i].t /CLOCKS_PER_SEC
            << " seconds" << endl;
     delete[] table;
     return 0;
}


